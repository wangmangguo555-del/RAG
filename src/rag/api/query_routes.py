from __future__ import annotations

from fastapi import APIRouter, Depends

from rag.api.dependencies import get_container
from rag.api.schemas import (
    CitationResponse,
    QueryRequest,
    QueryResponse,
    SearchHitResponse,
)
from rag.container import Container
from rag.domain.models import SearchFilter

router = APIRouter(tags=["query"])


def _filters(request: QueryRequest) -> SearchFilter:
    return SearchFilter(
        repo_ids=tuple(request.repo_ids),
        path_prefixes=tuple(request.path_prefixes),
        languages=tuple(request.languages),
    )


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest, container: Container = Depends(get_container)
) -> QueryResponse:
    result = await container.query_service.answer(request.question, _filters(request))
    return QueryResponse(
        answer=result.answer,
        confidence=result.confidence,
        citations=[
            CitationResponse(
                id=citation.id,
                repo_id=citation.repo_id,
                commit_sha=citation.commit_sha,
                path=citation.path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                snippet=citation.snippet,
            )
            for citation in result.citations
        ],
        index_snapshots=list(result.snapshot_ids),
        timing_ms=result.timing_ms,
    )


@router.post("/search", response_model=list[SearchHitResponse])
async def search(
    request: QueryRequest, container: Container = Depends(get_container)
) -> list[SearchHitResponse]:
    hits = await container.query_service.search(request.question, _filters(request))
    return [
        SearchHitResponse(
            chunk_id=hit.chunk_id,
            repo_id=hit.repo_id,
            commit_sha=hit.commit_sha,
            path=hit.path,
            start_line=hit.start_line,
            end_line=hit.end_line,
            language=hit.language,
            symbol=hit.symbol,
            score=hit.score,
            source=hit.source,
            content=hit.content,
        )
        for hit in hits
    ]
