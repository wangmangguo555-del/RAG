from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from rag.application.query_service import QueryService
from rag.domain.models import Chunk, Repository, SearchFilter, SearchHit, SourceType
from rag.domain.ports import (
    EmbeddingPort,
    GenerationPort,
    LexicalStorePort,
    MetadataStorePort,
    VectorStorePort,
)
from rag.generation.prompt_builder import PromptBuilder
from rag.infrastructure.settings import RetrievalSettings


class _MetadataStub:
    def __init__(self) -> None:
        self.chunks: dict[str, Chunk] = {}

    async def list_repositories(self) -> list[Repository]:
        # 故意让低分仓库排在前面，用于证明最终排序不依赖注册顺序。
        return [
            Repository("repo-low", "Low", SourceType.WORKING_TREE, "."),
            Repository("repo-high", "High", SourceType.WORKING_TREE, "."),
        ]

    async def get_published_snapshot(self, repo_id: str) -> str | None:
        return {"repo-low": "snap-low", "repo-high": "snap-high"}.get(repo_id)

    async def get_chunks(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        return {chunk_id: self.chunks[chunk_id] for chunk_id in chunk_ids}

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"测试不应调用 MetadataStub.{name}")


class _VectorStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def search_snapshot(
        self,
        repo_id: str,
        snapshot_id: str,
        vector: list[float],
        filters: SearchFilter,
        limit: int,
    ) -> list[SearchHit]:
        del vector, filters, limit
        self.calls.append((repo_id, snapshot_id))
        score = 0.2 if repo_id == "repo-low" else 0.9
        chunk_id = f"chunk-{repo_id}"
        return [
            SearchHit(
                chunk_id=chunk_id,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                commit_sha="a" * 40,
                path=f"{repo_id}.py",
                start_line=1,
                end_line=2,
                score=score,
                source="dense",
                content_hash=chunk_id,
            )
        ]


class _EmbeddingStub:
    async def embed_query(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]


class _UnusedStub:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"测试不应调用 {name}")


@pytest.mark.asyncio
async def test_dense_search_uses_published_snapshots_and_global_score_order() -> None:
    metadata = _MetadataStub()
    vectors = _VectorStub()
    for repo_id, snapshot_id in (("repo-low", "snap-low"), ("repo-high", "snap-high")):
        chunk_id = f"chunk-{repo_id}"
        metadata.chunks[chunk_id] = Chunk(
            id=chunk_id,
            point_id="",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            commit_sha="a" * 40,
            path=f"{repo_id}.py",
            language="python",
            content="def search():\n    return True",
            embedding_text="",
            content_hash=chunk_id,
            start_line=1,
            end_line=2,
        )
    service = QueryService(
        metadata=cast(MetadataStorePort, metadata),
        lexical=cast(LexicalStorePort, _UnusedStub()),
        vectors=cast(VectorStorePort, vectors),
        embedding=cast(EmbeddingPort, _EmbeddingStub()),
        generation=cast(GenerationPort, _UnusedStub()),
        prompt_builder=PromptBuilder(Path(__file__).resolve().parents[2] / "prompts"),
        settings=RetrievalSettings(final_top_k=2),
    )

    hits = await service.search("search", SearchFilter(), mode="dense")

    assert vectors.calls == [("repo-low", "snap-low"), ("repo-high", "snap-high")]
    assert [hit.repo_id for hit in hits] == ["repo-high", "repo-low"]
