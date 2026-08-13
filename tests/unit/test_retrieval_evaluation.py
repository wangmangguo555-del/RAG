from pathlib import Path

import pytest

from rag.domain.models import GitBlob, Repository, SearchFilter, SearchHit, SourceType
from rag.evaluation.retrieval import (
    EvaluationCase,
    evaluate_retrieval,
    find_contaminated_evaluation_paths,
    load_evaluation_cases,
)


def _hit(path: str, start_line: int, end_line: int) -> SearchHit:
    return SearchHit(
        chunk_id=f"{path}:{start_line}",
        repo_id="sample-repo",
        snapshot_id="snapshot-1",
        commit_sha="abc123",
        path=path,
        start_line=start_line,
        end_line=end_line,
        score=1.0,
        source="fused",
    )


def test_load_evaluation_cases_rejects_answerable_case_without_evidence(tmp_path: Path) -> None:
    questions = tmp_path / "questions.jsonl"
    expected = tmp_path / "expected.jsonl"
    questions.write_text(
        '{"id":"q1","question":"What?","repo_id":"repo","should_answer":true}\n',
        encoding="utf-8",
    )
    expected.write_text('{"id":"q1","evidence":[]}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="has no expected evidence"):
        load_evaluation_cases(questions, expected)


def test_contamination_audit_uses_normal_discovery_policy(tmp_path: Path) -> None:
    evaluation_markdown = tmp_path / "evals" / "questions.md"
    evaluation_jsonl = tmp_path / "evals" / "questions.jsonl"
    repository = Repository(
        id="repo",
        name="repo",
        source_type=SourceType.WORKING_TREE,
        source_uri=str(tmp_path),
    )
    blobs = [
        GitBlob(path="evals/questions.md", blob_sha="a", size=100),
        GitBlob(path="evals/questions.jsonl", blob_sha="b", size=100),
    ]

    assert find_contaminated_evaluation_paths(
        repository,
        (evaluation_markdown, evaluation_jsonl),
        blobs,
        max_file_bytes=1_000,
    ) == ("evals/questions.md",)
    assert (
        find_contaminated_evaluation_paths(
            repository,
            (evaluation_markdown,),
            blobs,
            max_file_bytes=1_000,
            ragignore_lines=("evals/**",),
        )
        == ()
    )


@pytest.mark.asyncio
async def test_evaluate_retrieval_calculates_explainable_metrics(tmp_path: Path) -> None:
    questions = tmp_path / "questions.jsonl"
    expected = tmp_path / "expected.jsonl"
    questions.write_text(
        '{"id":"q1","question":"Expired?","repo_id":"repo"}\n'
        '{"id":"q2","question":"Missing?","repo_id":"repo"}\n'
        '{"id":"q3","question":"Unknown?","repo_id":"repo","should_answer":false}\n',
        encoding="utf-8",
    )
    expected.write_text(
        '{"id":"q1","evidence":[{"path":"src/auth.py",'
        '"start_line":19,"end_line":20},{"path":"README.md",'
        '"start_line":5,"end_line":8}]}\n'
        '{"id":"q2","evidence":[{"path":"README.md",'
        '"start_line":5,"end_line":8}]}\n'
        '{"id":"q3","evidence":[]}\n',
        encoding="utf-8",
    )
    cases = load_evaluation_cases(questions, expected)

    async def search(question: str, filters: SearchFilter, top_k: int) -> list[SearchHit]:
        assert filters.repo_ids == ("repo",)
        assert top_k == 10
        if question == "Expired?":
            return [_hit("other.py", 1, 2), _hit("src/auth.py", 15, 21)]
        return [_hit("other.py", 1, 2)]

    report = await evaluate_retrieval(cases, search)

    summary = report["summary"]
    assert summary["case_count"] == 3
    assert summary["answerable_case_count"] == 2
    assert summary["unanswerable_case_count"] == 1
    assert summary["top_k"] == 10
    assert summary["hit_at_k"] == 0.5
    assert summary["target_recall_at_k"] == 0.25
    assert summary["mrr_at_k"] == 0.25
    assert summary["ndcg_at_k"] == pytest.approx(0.1934264)
    assert summary["unanswerable_no_hit_rate_at_k"] == 0.0
    assert summary["unanswerable_candidate_rate_at_k"] == 1.0
    assert summary["evidence_recall_at_k"] == summary["hit_at_k"]
    assert report["details"][0]["matched_ranks"] == [2]
    assert report["details"][0]["target_match_ranks"] == [2, None]
    assert report["details"][0]["target_recall_at_k"] == 0.5
    assert report["details"][2]["hit_at_k"] is None
    assert report["details"][2]["unanswerable_no_hit_at_k"] is False
    assert report["deprecated_metrics"]["evidence_recall_at_k"].startswith("compatibility alias")


@pytest.mark.asyncio
async def test_unanswerable_no_hit_rate_counts_empty_results() -> None:
    cases = [
        EvaluationCase(
            id="q1",
            question="Unknown?",
            repo_id="repo",
            expected_evidence=(),
            should_answer=False,
        )
    ]

    async def search(question: str, filters: SearchFilter, top_k: int) -> list[SearchHit]:
        return []

    report = await evaluate_retrieval(cases, search, top_k=5)

    assert report["summary"]["unanswerable_no_hit_rate_at_k"] == 1.0
    assert report["summary"]["unanswerable_candidate_rate_at_k"] == 0.0
    assert report["details"][0]["returned_candidate_count"] == 0
    assert report["details"][0]["unanswerable_no_hit_at_k"] is True
