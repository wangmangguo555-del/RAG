from pathlib import Path

import pytest

from rag.domain.models import SearchFilter, SearchHit
from rag.evaluation.retrieval import evaluate_retrieval, load_evaluation_cases


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


@pytest.mark.asyncio
async def test_evaluate_retrieval_calculates_recall_and_mrr(tmp_path: Path) -> None:
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
        '"start_line":19,"end_line":20}]}\n'
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

    assert report["summary"] == {
        "case_count": 3,
        "answerable_case_count": 2,
        "unanswerable_case_count": 1,
        "top_k": 10,
        "evidence_recall_at_k": 0.5,
        "mrr_at_k": 0.25,
    }
    assert report["details"][0]["matched_ranks"] == [2]
    assert report["details"][2]["recall_at_k"] is None
