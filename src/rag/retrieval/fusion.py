from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace

from rag.domain.models import SearchHit


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[SearchHit]], *, k: int = 60, limit: int = 20
) -> list[SearchHit]:
    scores: dict[str, float] = defaultdict(float)
    representatives: dict[str, SearchHit] = {}
    sources: dict[str, set[str]] = defaultdict(set)
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            scores[hit.chunk_id] += 1.0 / (k + rank)
            representatives.setdefault(hit.chunk_id, hit)
            sources[hit.chunk_id].add(hit.source)
    ordered = sorted(scores, key=scores.__getitem__, reverse=True)[:limit]
    return [
        replace(
            representatives[chunk_id],
            score=scores[chunk_id],
            source="+".join(sorted(sources[chunk_id])),
        )
        for chunk_id in ordered
    ]


def diversify(
    hits: Sequence[SearchHit], *, final_k: int, max_chunks_per_file: int
) -> list[SearchHit]:
    selected: list[SearchHit] = []
    per_file: dict[tuple[str, str], int] = defaultdict(int)
    seen_content: set[str] = set()
    for hit in hits:
        if hit.content_hash and hit.content_hash in seen_content:
            continue
        key = (hit.repo_id, hit.path)
        if per_file[key] >= max_chunks_per_file:
            continue
        selected.append(hit)
        per_file[key] += 1
        if hit.content_hash:
            seen_content.add(hit.content_hash)
        if len(selected) >= final_k:
            break
    return selected
