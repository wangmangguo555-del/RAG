from __future__ import annotations

from typing import Any, cast

import pytest

from rag.application.index_service import IndexService
from rag.domain.models import GitBlob, IndexJob, JobStatus, Repository, SourceType
from rag.domain.ports import EmbeddingPort, GitSourcePort, MetadataStorePort, VectorStorePort
from rag.infrastructure.settings import IngestionSettings


class _MetadataStub:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.repository = Repository(
            id="demo",
            name="Demo",
            source_type=SourceType.WORKING_TREE,
            source_uri=".",
        )
        self.chunk_count = 0
        self.published = False

    async def get_job(self, job_id: str) -> IndexJob | None:
        return IndexJob(job_id, "demo", "HEAD", JobStatus.RUNNING, attempt=1)

    async def get_repository(self, repo_id: str) -> Repository | None:
        return self.repository if repo_id == "demo" else None

    async def record_job_commit(self, job_id: str, commit_sha: str) -> None:
        del job_id, commit_sha

    async def record_job_snapshot(self, job_id: str, snapshot_id: str) -> None:
        del job_id, snapshot_id

    async def find_published_snapshot(
        self, repo_id: str, commit_sha: str, index_version: str
    ) -> str | None:
        del repo_id, commit_sha, index_version
        return None

    async def create_snapshot(self, repo_id: str, commit_sha: str, index_version: str) -> str:
        del repo_id, commit_sha, index_version
        self.events.append("create_snapshot")
        return "snapshot-1"

    async def save_file(self, snapshot_id: str, **values: Any) -> None:
        del snapshot_id, values

    async def save_chunks(self, chunks: list[Any]) -> None:
        self.chunk_count += len(chunks)
        self.events.append("save_chunks")

    async def count_snapshot_chunks(self, snapshot_id: str) -> int:
        del snapshot_id
        return self.chunk_count

    async def publish_snapshot(self, snapshot_id: str, stats: dict[str, int]) -> None:
        del snapshot_id, stats
        self.published = True
        self.events.append("publish_snapshot")

    async def complete_job(self, job_id: str, **values: Any) -> None:
        del job_id, values
        self.events.append("complete_job")

    async def is_snapshot_published(self, snapshot_id: str) -> bool:
        del snapshot_id
        return self.published

    async def fail_snapshot(self, snapshot_id: str, message: str) -> None:
        del snapshot_id, message
        self.events.append("fail_snapshot")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"测试不应调用 MetadataStub.{name}")


class _GitStub:
    async def resolve_ref(self, repository: Repository, ref: str) -> str:
        del repository, ref
        return "a" * 40

    async def list_blobs(self, repository: Repository, commit_sha: str) -> list[GitBlob]:
        del repository, commit_sha
        return [GitBlob("service.py", "blob-1", 80)]

    async def read_blob(self, repository: Repository, blob_sha: str) -> bytes:
        del repository, blob_sha
        return b"def answer_question(question: str) -> str:\n    return question.strip()\n"


class _EmbeddingStub:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class _VectorStub:
    def __init__(self, events: list[str], *, validation_error: bool = False) -> None:
        self.events = events
        self.validation_error = validation_error

    async def create_snapshot_collection(
        self, repo_id: str, snapshot_id: str, vector_size: int
    ) -> str:
        del repo_id, snapshot_id, vector_size
        self.events.append("create_collection")
        return "repo_demo__snap_snapshot-1"

    async def upsert(
        self, collection_name: str, chunks: list[Any], vectors: list[list[float]]
    ) -> None:
        del collection_name, chunks, vectors
        self.events.append("upsert")

    async def validate_snapshot_collection(
        self, collection_name: str, *, expected_points: int, vector_size: int
    ) -> None:
        del collection_name, expected_points, vector_size
        self.events.append("validate_collection")
        if self.validation_error:
            raise ValueError("向量数量不一致")


def _service(metadata: _MetadataStub, vectors: _VectorStub) -> IndexService:
    return IndexService(
        metadata=cast(MetadataStorePort, metadata),
        git=cast(GitSourcePort, _GitStub()),
        embedding=cast(EmbeddingPort, _EmbeddingStub()),
        vectors=cast(VectorStorePort, vectors),
        settings=IngestionSettings(chunk_min_tokens=1),
        embedding_fingerprint="test-model",
    )


@pytest.mark.asyncio
async def test_snapshot_is_validated_before_publish_and_job_completion() -> None:
    events: list[str] = []
    metadata = _MetadataStub(events)

    stats = await _service(metadata, _VectorStub(events)).execute_job("job-1")

    assert stats["chunks"] == 1
    assert events.index("validate_collection") < events.index("publish_snapshot")
    assert events.index("publish_snapshot") < events.index("complete_job")


@pytest.mark.asyncio
async def test_validation_failure_keeps_snapshot_unpublished() -> None:
    events: list[str] = []
    metadata = _MetadataStub(events)

    with pytest.raises(ValueError, match="向量数量不一致"):
        await _service(metadata, _VectorStub(events, validation_error=True)).execute_job("job-1")

    assert "publish_snapshot" not in events
    assert events[-1] == "fail_snapshot"
