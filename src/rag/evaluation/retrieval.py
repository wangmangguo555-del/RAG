from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rag.domain.models import SearchFilter, SearchHit


@dataclass(frozen=True, slots=True)
class EvidenceTarget:
    path: str
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    question: str
    repo_id: str
    expected_evidence: tuple[EvidenceTarget, ...]
    should_answer: bool = True


SearchFunction = Callable[
    [str, SearchFilter, int],
    Awaitable[list[SearchHit]],
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}:{line_number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise TypeError(f"expected an object in {path}:{line_number}")
        rows.append(value)
    return rows


def _index_by_id(rows: Sequence[dict[str, Any]], path: Path) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"every row in {path} must have a non-empty string id")
        if case_id in indexed:
            raise ValueError(f"duplicate evaluation id in {path}: {case_id}")
        indexed[case_id] = row
    return indexed


def _parse_targets(row: Mapping[str, Any], case_id: str) -> tuple[EvidenceTarget, ...]:
    raw_targets = row.get("evidence")
    if raw_targets is None:
        raw_targets = [{"path": path} for path in row.get("expected_paths", [])]
    if not isinstance(raw_targets, list):
        raise TypeError(f"expected evidence list for evaluation id {case_id}")

    targets: list[EvidenceTarget] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, dict) or not isinstance(raw_target.get("path"), str):
            raise TypeError(f"invalid evidence target for evaluation id {case_id}")
        start_line = raw_target.get("start_line")
        end_line = raw_target.get("end_line")
        if start_line is not None and (not isinstance(start_line, int) or start_line < 1):
            raise ValueError(f"invalid start_line for evaluation id {case_id}")
        if end_line is not None and (not isinstance(end_line, int) or end_line < 1):
            raise ValueError(f"invalid end_line for evaluation id {case_id}")
        if start_line is not None and end_line is not None and start_line > end_line:
            raise ValueError(f"start_line exceeds end_line for evaluation id {case_id}")
        targets.append(
            EvidenceTarget(
                path=raw_target["path"].replace("\\", "/"),
                start_line=start_line,
                end_line=end_line,
            )
        )
    return tuple(targets)


def load_evaluation_cases(questions_path: Path, expected_path: Path) -> list[EvaluationCase]:
    questions = _read_jsonl(questions_path)
    expected = _index_by_id(_read_jsonl(expected_path), expected_path)
    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()

    for row in questions:
        case_id = row.get("id")
        question = row.get("question")
        repo_id = row.get("repo_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"every row in {questions_path} must have a non-empty string id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate evaluation id in {questions_path}: {case_id}")
        seen_ids.add(case_id)
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"missing question for evaluation id {case_id}")
        if not isinstance(repo_id, str) or not repo_id.strip():
            raise ValueError(f"missing repo_id for evaluation id {case_id}")
        expected_row = expected.get(case_id, {})
        should_answer = row.get("should_answer", True)
        if not isinstance(should_answer, bool):
            raise TypeError(f"should_answer must be boolean for evaluation id {case_id}")
        targets = _parse_targets(expected_row, case_id)
        if should_answer and not targets:
            raise ValueError(f"answerable evaluation id {case_id} has no expected evidence")
        cases.append(
            EvaluationCase(
                id=case_id,
                question=question.strip(),
                repo_id=repo_id.strip(),
                expected_evidence=targets,
                should_answer=should_answer,
            )
        )

    unknown_ids = sorted(set(expected) - seen_ids)
    if unknown_ids:
        raise ValueError(f"expected evidence has unknown ids: {', '.join(unknown_ids)}")
    return cases


def evidence_matches(hit: SearchHit, target: EvidenceTarget) -> bool:
    if hit.path.replace("\\", "/") != target.path:
        return False
    if target.start_line is None and target.end_line is None:
        return True
    target_start = target.start_line or target.end_line
    target_end = target.end_line or target.start_line
    assert target_start is not None and target_end is not None
    return hit.start_line <= target_end and hit.end_line >= target_start


async def evaluate_retrieval(
    cases: Sequence[EvaluationCase],
    search: SearchFunction,
    *,
    top_k: int = 10,
    repo_id_override: str | None = None,
    configuration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    details: list[dict[str, Any]] = []
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    for case in cases:
        repo_id = repo_id_override or case.repo_id
        hits = (await search(case.question, SearchFilter(repo_ids=(repo_id,)), top_k))[:top_k]
        matched_ranks = [
            rank
            for rank, hit in enumerate(hits, 1)
            if any(evidence_matches(hit, target) for target in case.expected_evidence)
        ]
        if case.should_answer:
            recall = 1.0 if matched_ranks else 0.0
            reciprocal_rank = 1.0 / matched_ranks[0] if matched_ranks else 0.0
            recalls.append(recall)
            reciprocal_ranks.append(reciprocal_rank)
        else:
            recall = None
            reciprocal_rank = None
        details.append(
            {
                "id": case.id,
                "question": case.question,
                "repo_id": repo_id,
                "should_answer": case.should_answer,
                "expected_evidence": [asdict(target) for target in case.expected_evidence],
                "matched_ranks": matched_ranks,
                "recall_at_k": recall,
                "reciprocal_rank": reciprocal_rank,
                "hits": [
                    {
                        "rank": rank,
                        "path": hit.path,
                        "start_line": hit.start_line,
                        "end_line": hit.end_line,
                        "score": hit.score,
                        "source": hit.source,
                        "chunk_id": hit.chunk_id,
                    }
                    for rank, hit in enumerate(hits, 1)
                ],
            }
        )

    answerable_count = len(recalls)
    summary = {
        "case_count": len(cases),
        "answerable_case_count": answerable_count,
        "unanswerable_case_count": len(cases) - answerable_count,
        "top_k": top_k,
        "evidence_recall_at_k": sum(recalls) / answerable_count if answerable_count else None,
        "mrr_at_k": (sum(reciprocal_ranks) / answerable_count if answerable_count else None),
    }
    report: dict[str, Any] = {"summary": summary, "details": details}
    if configuration is not None:
        report["configuration"] = dict(configuration)
    return report
