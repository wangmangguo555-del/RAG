from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from pathlib import PurePosixPath

from rag.domain.models import SearchHit

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-/]{2,}")


def _query_identifiers(question: str) -> set[str]:
    identifiers: set[str] = set()
    for match in _IDENTIFIER.finditer(question):
        value = match.group(0)
        code_shaped = any(marker in value for marker in ("_", ".", "/", "-"))
        camel_or_acronym = any(character.isupper() for character in value[1:])
        if code_shaped or camel_or_acronym:
            identifiers.add(value.casefold())
    return identifiers


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


def boost_exact_matches(
    hits: Sequence[SearchHit],
    question: str,
    *,
    symbol_boost: float,
    path_boost: float,
) -> list[SearchHit]:
    identifiers = _query_identifiers(question)
    if not identifiers or (symbol_boost == 0 and path_boost == 0):
        return list(hits)

    boosted: list[SearchHit] = []
    for hit in hits:
        score = hit.score
        symbol = (hit.symbol or "").casefold()
        normalized_path = hit.path.replace("\\", "/").casefold()
        path = PurePosixPath(normalized_path)
        path_terms = {normalized_path, path.name, path.stem, *path.parts}
        if symbol and symbol in identifiers:
            score += symbol_boost
        if identifiers & path_terms:
            score += path_boost
        boosted.append(replace(hit, score=score))
    return sorted(boosted, key=lambda hit: hit.score, reverse=True)
