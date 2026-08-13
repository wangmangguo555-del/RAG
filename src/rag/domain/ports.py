from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from rag.domain.models import (
    Chunk,
    GitBlob,
    IndexJob,
    Repository,
    SearchFilter,
    SearchHit,
    SnapshotGcCandidate,
    SnapshotRef,
)


class GitSourcePort(Protocol):
    async def resolve_ref(self, repository: Repository, ref: str) -> str: ...

    async def list_blobs(self, repository: Repository, commit_sha: str) -> list[GitBlob]: ...

    async def read_blob(self, repository: Repository, blob_sha: str) -> bytes: ...


class EmbeddingPort(Protocol):
    async def health(self) -> bool: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class GenerationPort(Protocol):
    async def health(self) -> bool: ...

    async def answer(self, system_prompt: str, user_prompt: str) -> str: ...


class VectorStorePort(Protocol):
    async def health(self) -> bool: ...

    async def create_snapshot_collection(
        self, repo_id: str, snapshot_id: str, vector_size: int
    ) -> str: ...

    def collection_name(self, repo_id: str, snapshot_id: str) -> str: ...

    async def upsert(
        self, collection_name: str, chunks: Sequence[Chunk], vectors: Sequence[list[float]]
    ) -> None: ...

    async def validate_snapshot_collection(
        self, collection_name: str, *, expected_points: int, vector_size: int
    ) -> None: ...

    async def snapshot_exists(self, repo_id: str, snapshot_id: str) -> bool: ...

    async def search_snapshot(
        self,
        repo_id: str,
        snapshot_id: str,
        vector: list[float],
        filters: SearchFilter,
        limit: int,
    ) -> list[SearchHit]: ...


class MetadataStorePort(Protocol):
    async def initialize(self) -> None: ...

    async def register_repository(self, repository: Repository) -> None: ...

    async def get_repository(self, repo_id: str) -> Repository | None: ...

    async def list_repositories(self) -> list[Repository]: ...

    async def create_job(self, repo_id: str, requested_ref: str) -> str: ...

    async def claim_next_job(self) -> IndexJob | None: ...

    async def record_job_commit(self, job_id: str, commit_sha: str) -> None: ...

    async def record_job_snapshot(self, job_id: str, snapshot_id: str) -> None: ...

    async def heartbeat_job(self, job_id: str) -> None: ...

    async def recover_stale_jobs(self, stale_before: str, max_attempts: int) -> dict[str, int]: ...

    async def retry_or_fail_job(
        self,
        job_id: str,
        *,
        retryable: bool,
        max_attempts: int,
        retry_delay_seconds: float,
        error_code: str,
        error_message: str,
    ) -> str: ...

    async def get_job(self, job_id: str) -> IndexJob | None: ...

    async def complete_job(
        self,
        job_id: str,
        *,
        success: bool,
        commit_sha: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    async def create_snapshot(self, repo_id: str, commit_sha: str, index_version: str) -> str: ...

    async def find_published_snapshot(
        self, repo_id: str, commit_sha: str, index_version: str
    ) -> str | None: ...

    async def publish_snapshot(self, snapshot_id: str, stats: dict[str, int]) -> None: ...

    async def fail_snapshot(self, snapshot_id: str, message: str) -> None: ...

    async def get_published_snapshot(self, repo_id: str) -> str | None: ...

    async def list_published_snapshots(self) -> list[SnapshotRef]: ...

    async def is_snapshot_published(self, snapshot_id: str) -> bool: ...

    async def count_snapshot_chunks(self, snapshot_id: str) -> int: ...

    async def plan_snapshot_gc(
        self,
        *,
        retain_successful: int,
        superseded_before: str,
        failed_before: str,
    ) -> list[SnapshotGcCandidate]: ...

    async def save_file(
        self,
        snapshot_id: str,
        *,
        path: str,
        blob_sha: str,
        language: str,
        parse_status: str,
        content_bytes: int,
    ) -> None: ...

    async def save_chunks(self, chunks: Sequence[Chunk]) -> None: ...

    async def get_chunks(self, chunk_ids: Sequence[str]) -> dict[str, Chunk]: ...


class LexicalStorePort(Protocol):
    async def search_lexical(
        self,
        query: str,
        snapshot_ids: Sequence[str],
        filters: SearchFilter,
        limit: int,
    ) -> list[SearchHit]: ...


class JobStreamPort(Protocol):
    async def watch(self) -> AsyncIterator[IndexJob]: ...
