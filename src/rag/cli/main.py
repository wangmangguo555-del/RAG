from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Literal, cast

import typer

from rag.container import Container
from rag.domain.models import Repository, SearchFilter, SourceType
from rag.evaluation.retrieval import (
    evaluate_retrieval,
    find_contaminated_evaluation_paths,
    load_evaluation_cases,
)
from rag.infrastructure.settings import load_settings
from rag.ingestion.discovery import decode_text
from rag.worker.main import run_worker

app = typer.Typer(no_args_is_help=True, help="Local RAG administration CLI")
PROJECT_ROOT = Path(__file__).resolve().parents[3]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


def _build_container() -> Container:
    config_path = os.getenv("RAG_CONFIG", str(PROJECT_ROOT / "config" / "default.yaml"))
    return Container.build(load_settings(config_path), PROJECT_ROOT)


@app.command("init-db")
def init_db() -> None:
    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            typer.echo(f"Initialized SQLite: {container.settings.sqlite.path}")
        finally:
            await container.close()

    asyncio.run(run())


@app.command("register-web")
def register_web(
    repo_id: str = typer.Option(..., "--id"),
    url: str = typer.Option(..., "--url"),
    name: str | None = typer.Option(None),
) -> None:
    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            await container.metadata.register_repository(
                Repository(
                    id=repo_id,
                    name=name or repo_id,
                    source_type=SourceType.WEB_PAGE,
                    source_uri=url,
                    default_ref="live",
                )
            )
            typer.echo(f"Registered web source: {repo_id}")
        finally:
            await container.close()

    asyncio.run(run())


@app.command("register-repo")
def register_repo(
    repo_id: str = typer.Option(..., "--id"),
    path: Path = typer.Option(..., exists=True, file_okay=False, resolve_path=True),
    name: str | None = typer.Option(None),
    ref: str = typer.Option("HEAD"),
) -> None:
    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            await container.metadata.register_repository(
                Repository(
                    id=repo_id,
                    name=name or repo_id,
                    source_type=SourceType.WORKING_TREE,
                    source_uri=str(path),
                    default_ref=ref,
                )
            )
            typer.echo(f"Registered repository: {repo_id}")
        finally:
            await container.close()

    asyncio.run(run())


@app.command("index")
def index(repo_id: str, ref: str | None = None, run_now: bool = True) -> None:
    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            job_id = await container.index_service.submit(repo_id, ref)
            typer.echo(f"Created index job: {job_id}")
        finally:
            await container.close()
        if run_now:
            await run_worker(once=True)

    asyncio.run(run())


@app.command("worker")
def worker(once: bool = typer.Option(False)) -> None:
    asyncio.run(run_worker(once=once))


@app.command("gc")
def gc_snapshots(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="仅输出快照回收候选；阶段 A 尚不执行物理删除。",
    ),
) -> None:
    """只生成快照回收计划；阶段 A 默认不自动删除任何业务数据。"""

    if not dry_run:
        raise typer.BadParameter("当前版本仅支持 --dry-run，不允许直接删除快照")

    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            settings = container.settings.ingestion
            now = datetime.now(UTC)
            candidates = await container.metadata.plan_snapshot_gc(
                retain_successful=settings.snapshot_retained_successful,
                superseded_before=(
                    now - timedelta(seconds=settings.snapshot_superseded_grace_seconds)
                ).isoformat(),
                failed_before=(
                    now - timedelta(seconds=settings.snapshot_failed_grace_seconds)
                ).isoformat(),
            )
            if not candidates:
                typer.echo("No snapshots are eligible for collection.")
                return
            typer.echo("Dry-run only; no SQLite rows or Qdrant collections were deleted.")
            for candidate in candidates:
                collection_name = container.vectors.collection_name(candidate.repo_id, candidate.id)
                typer.echo(
                    f"{candidate.status.value}\t{candidate.repo_id}\t{candidate.id}\t"
                    f"{collection_name}\t{candidate.reason}"
                )
        finally:
            await container.close()

    asyncio.run(run())


@app.command("search")
def search(question: str, repo_id: list[str] = typer.Option([], "--repo")) -> None:
    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            hits = await container.query_service.search(
                question, SearchFilter(repo_ids=tuple(repo_id))
            )
            for hit in hits:
                typer.echo(
                    f"{hit.score:.6f}\t{hit.source}\t"
                    f"{hit.repo_id}:{hit.path}:{hit.start_line}-{hit.end_line}"
                )
                typer.echo(hit.content[:300].replace("\n", " "))
        finally:
            await container.close()

    asyncio.run(run())


@app.command("query")
def query(question: str, repo_id: list[str] = typer.Option([], "--repo")) -> None:
    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            result = await container.query_service.answer(
                question, SearchFilter(repo_ids=tuple(repo_id))
            )
            typer.echo(result.answer)
            for citation in result.citations:
                typer.echo(
                    f"[{citation.id}] {citation.repo_id}:{citation.path}:"
                    f"{citation.start_line}-{citation.end_line}@{citation.commit_sha[:12]}"
                )
        finally:
            await container.close()

    asyncio.run(run())


@app.command("evaluate")
def evaluate(
    questions: Path = typer.Option(
        PROJECT_ROOT / "evals" / "questions.jsonl",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    expected: Path = typer.Option(
        PROJECT_ROOT / "evals" / "expected_evidence.jsonl",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        PROJECT_ROOT / "data" / "evals" / "retrieval-latest.json",
        dir_okay=False,
        resolve_path=True,
    ),
    top_k: int = typer.Option(10, min=1),
    repo_id: str | None = typer.Option(None, "--repo"),
    mode: str = typer.Option("hybrid", help="Retrieval mode: hybrid, dense, or lexical"),
) -> None:
    """Evaluate retrieval against annotated evidence without invoking the LLM."""

    async def run() -> None:
        if mode not in {"hybrid", "dense", "lexical"}:
            raise typer.BadParameter("must be hybrid, dense, or lexical", param_hint="--mode")
        retrieval_mode = cast(Literal["hybrid", "dense", "lexical"], mode)
        cases = load_evaluation_cases(questions, expected)
        container = _build_container()
        try:
            await container.metadata.initialize()
            evaluated_repo_ids = sorted({repo_id or case.repo_id for case in cases})
            published_snapshots = {
                snapshot.repo_id: snapshot
                for snapshot in await container.metadata.list_published_snapshots()
            }
            audited_repositories: list[dict[str, str]] = []
            for evaluated_repo_id in evaluated_repo_ids:
                repository = await container.metadata.get_repository(evaluated_repo_id)
                if repository is None:
                    raise typer.BadParameter(
                        f"repository is not registered: {evaluated_repo_id}",
                        param_hint="--repo",
                    )
                published_snapshot = published_snapshots.get(evaluated_repo_id)
                if published_snapshot is None:
                    raise typer.BadParameter(
                        f"repository has no published snapshot: {evaluated_repo_id}",
                        param_hint="--repo",
                    )
                if repository.source_type not in {
                    SourceType.WORKING_TREE,
                    SourceType.LOCAL_MIRROR,
                }:
                    audited_repositories.append(
                        {
                            "repo_id": evaluated_repo_id,
                            "commit_sha": published_snapshot.commit_sha,
                            "status": "not_applicable",
                        }
                    )
                    continue
                commit_sha = published_snapshot.commit_sha
                blobs = await container.sources.list_blobs(repository, commit_sha)
                ragignore_lines: tuple[str, ...] = ()
                ragignore_blob = next((blob for blob in blobs if blob.path == ".ragignore"), None)
                if ragignore_blob is not None:
                    ragignore_text = decode_text(
                        await container.sources.read_blob(repository, ragignore_blob.blob_sha)
                    )
                    if ragignore_text is not None:
                        ragignore_lines = tuple(
                            line.strip()
                            for line in ragignore_text.splitlines()
                            if line.strip() and not line.lstrip().startswith("#")
                        )
                contaminated_paths = find_contaminated_evaluation_paths(
                    repository,
                    (questions, expected),
                    blobs,
                    max_file_bytes=container.settings.ingestion.max_file_bytes,
                    ragignore_lines=ragignore_lines,
                )
                if contaminated_paths:
                    raise typer.BadParameter(
                        "evaluation data would be indexed by "
                        f"{evaluated_repo_id}: {', '.join(contaminated_paths)}; "
                        "exclude these paths before benchmarking",
                        param_hint="--questions/--expected",
                    )
                audited_repositories.append(
                    {
                        "repo_id": evaluated_repo_id,
                        "commit_sha": commit_sha,
                        "status": "passed",
                    }
                )
            report = await evaluate_retrieval(
                cases,
                partial(container.query_service.search, mode=retrieval_mode),
                top_k=top_k,
                repo_id_override=repo_id,
                configuration={
                    "embedding_fingerprint": container.settings.embedding.fingerprint,
                    "chunker_version": container.settings.ingestion.chunker_version,
                    "mode": retrieval_mode,
                    "retrieval": container.settings.retrieval.model_dump(mode="json"),
                    "evaluation_contamination_audit": {
                        "status": "passed",
                        "repositories": audited_repositories,
                    },
                },
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            summary = report["summary"]
            hit_at_k = summary["hit_at_k"]
            target_recall = summary["target_recall_at_k"]
            mrr = summary["mrr_at_k"]
            ndcg = summary["ndcg_at_k"]
            unanswerable_candidate_rate = summary["unanswerable_candidate_rate_at_k"]
            typer.echo(
                f"Cases: {summary['case_count']} ({summary['answerable_case_count']} scored)"
            )
            typer.echo(f"Hit@{top_k}: {hit_at_k:.3f}" if hit_at_k is not None else "Hit: n/a")
            typer.echo(
                f"Target Recall@{top_k}: {target_recall:.3f}"
                if target_recall is not None
                else "Target Recall: n/a"
            )
            typer.echo(f"MRR@{top_k}: {mrr:.3f}" if mrr is not None else "MRR: n/a")
            typer.echo(f"nDCG@{top_k}: {ndcg:.3f}" if ndcg is not None else "nDCG: n/a")
            typer.echo(
                f"Unanswerable Candidate Rate@{top_k}: {unanswerable_candidate_rate:.3f}"
                if unanswerable_candidate_rate is not None
                else "Unanswerable Candidate Rate: n/a"
            )
            typer.echo(f"Report: {output}")
        finally:
            await container.close()

    asyncio.run(run())


@app.command("doctor")
def doctor() -> None:
    async def run() -> None:
        container = _build_container()
        try:
            await container.metadata.initialize()
            checks = {
                "sqlite": await container.metadata.health(),
                "qdrant": await container.vectors.health(),
                "llm": await container.generation.health(),
                "embedding": await container.embeddings.health(),
            }
            for name, ok in checks.items():
                typer.echo(f"{name:10} {'OK' if ok else 'FAILED'}")
            if not all(checks.values()):
                raise typer.Exit(1)
        finally:
            await container.close()

    asyncio.run(run())


if __name__ == "__main__":
    app()
