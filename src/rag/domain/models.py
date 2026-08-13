from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    WORKING_TREE = "working_tree"
    LOCAL_MIRROR = "local_mirror"
    REMOTE_CLONE = "remote_clone"
    WEB_PAGE = "web_page"


class SnapshotStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    VALIDATING = "validating"
    PUBLISHED = "published"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Repository:
    id: str
    name: str
    source_type: SourceType
    source_uri: str
    default_ref: str = "HEAD"
    enabled: bool = True
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GitBlob:
    path: str
    blob_sha: str
    size: int


@dataclass(frozen=True, slots=True)
class SourceDocument:
    repo_id: str
    commit_sha: str
    path: str
    blob_sha: str
    language: str
    content: str
    parse_status: str = "parsed"


@dataclass(frozen=True, slots=True)
class DocumentNode:
    text: str
    start_line: int
    end_line: int
    node_type: str = "section"
    symbol: str | None = None
    parent_context: str | None = None


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    point_id: str
    repo_id: str
    snapshot_id: str
    commit_sha: str
    path: str
    language: str
    content: str
    embedding_text: str
    content_hash: str
    start_line: int
    end_line: int
    symbol: str | None = None
    node_type: str = "section"
    is_test: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchFilter:
    repo_ids: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: str
    repo_id: str
    snapshot_id: str
    commit_sha: str
    path: str
    start_line: int
    end_line: int
    score: float
    source: str
    language: str = "text"
    symbol: str | None = None
    content: str = ""
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Citation:
    id: str
    repo_id: str
    commit_sha: str
    path: str
    start_line: int
    end_line: int
    snippet: str


@dataclass(frozen=True, slots=True)
class QueryResult:
    answer: str
    confidence: str
    citations: tuple[Citation, ...]
    snapshot_ids: tuple[str, ...]
    timing_ms: dict[str, int]


@dataclass(frozen=True, slots=True)
class IndexJob:
    id: str
    repo_id: str
    requested_ref: str
    status: JobStatus
    resolved_commit_sha: str | None = None
    error_code: str | None = None
    error_message: str | None = None
