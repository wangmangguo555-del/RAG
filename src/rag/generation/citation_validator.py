from __future__ import annotations

import re

from rag.domain.models import Chunk, Citation

_CITATION = re.compile(r"\[(E\d+)]")


def validate_citations(
    answer: str, evidence_map: dict[str, Chunk]
) -> tuple[str, tuple[Citation, ...]]:
    referenced: list[str] = []
    for match in _CITATION.finditer(answer):
        evidence_id = match.group(1)
        if evidence_id in evidence_map and evidence_id not in referenced:
            referenced.append(evidence_id)
    citations = tuple(
        Citation(
            id=evidence_id,
            repo_id=evidence_map[evidence_id].repo_id,
            commit_sha=evidence_map[evidence_id].commit_sha,
            path=evidence_map[evidence_id].path,
            start_line=evidence_map[evidence_id].start_line,
            end_line=evidence_map[evidence_id].end_line,
            snippet=evidence_map[evidence_id].content[:500],
        )
        for evidence_id in referenced
    )
    return answer, citations
