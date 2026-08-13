from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rag.domain.models import SourceType


class RepositoryCreate(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType = SourceType.WORKING_TREE
    source_uri: str
    default_ref: str = "HEAD"
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class RepositoryResponse(RepositoryCreate):
    enabled: bool = True


class IndexRequest(BaseModel):
    ref: str | None = None


class JobResponse(BaseModel):
    id: str
    repo_id: str
    requested_ref: str
    status: str
    resolved_commit_sha: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10_000)
    repo_ids: list[str] = Field(default_factory=list)
    path_prefixes: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    debug: bool = False


class CitationResponse(BaseModel):
    id: str
    repo_id: str
    commit_sha: str
    path: str
    start_line: int
    end_line: int
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    confidence: str
    citations: list[CitationResponse]
    index_snapshots: list[str]
    timing_ms: dict[str, int]


class SearchHitResponse(BaseModel):
    chunk_id: str
    repo_id: str
    commit_sha: str
    path: str
    start_line: int
    end_line: int
    language: str
    symbol: str | None
    score: float
    source: str
    content: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, Any] = Field(default_factory=dict)
