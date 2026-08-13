from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import typer

from rag.container import Container
from rag.domain.models import Repository, SearchFilter, SourceType
from rag.evaluation.retrieval import evaluate_retrieval, load_evaluation_cases
from rag.infrastructure.settings import load_settings
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
) -> None:
    """Evaluate retrieval against annotated evidence without invoking the LLM."""

    async def run() -> None:
        cases = load_evaluation_cases(questions, expected)
        container = _build_container()
        try:
            await container.metadata.initialize()
            report = await evaluate_retrieval(
                cases,
                container.query_service.search,
                top_k=top_k,
                repo_id_override=repo_id,
                configuration={
                    "embedding_fingerprint": container.settings.embedding.fingerprint,
                    "chunker_version": container.settings.ingestion.chunker_version,
                    "retrieval": container.settings.retrieval.model_dump(mode="json"),
                },
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            summary = report["summary"]
            recall = summary["evidence_recall_at_k"]
            mrr = summary["mrr_at_k"]
            typer.echo(
                f"Cases: {summary['case_count']} ({summary['answerable_case_count']} scored)"
            )
            typer.echo(
                f"Evidence Recall@{top_k}: {recall:.3f}" if recall is not None else "Recall: n/a"
            )
            typer.echo(f"MRR@{top_k}: {mrr:.3f}" if mrr is not None else "MRR: n/a")
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
