from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from rag.domain.errors import IndexConsistencyError, VectorStoreUnavailableError
from rag.domain.models import Chunk, SearchFilter, SearchHit
from rag.infrastructure.settings import QdrantSettings


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)[:120]


class QdrantVectorStore:
    def __init__(self, settings: QdrantSettings) -> None:
        self.settings = settings
        self.client = QdrantClient(url=settings.url, api_key=settings.api_key, timeout=30)

    def collection_name(self, repo_id: str, snapshot_id: str) -> str:
        """由业务快照唯一推导物理 collection，避免额外保存第二份发布状态。"""

        return _safe_name(f"repo_{repo_id}__snap_{snapshot_id}")

    async def health(self) -> bool:
        try:
            await asyncio.to_thread(self.client.get_collections)
            return True
        except Exception:  # noqa: BLE001 - 健康检查必须把适配器异常收敛为不可用状态
            return False

    async def create_snapshot_collection(
        self, repo_id: str, snapshot_id: str, vector_size: int
    ) -> str:
        name = self.collection_name(repo_id, snapshot_id)
        distance = {
            "cosine": models.Distance.COSINE,
            "dot": models.Distance.DOT,
            "euclid": models.Distance.EUCLID,
        }.get(self.settings.distance.lower(), models.Distance.COSINE)
        try:
            exists = await asyncio.to_thread(self.client.collection_exists, name)
            if exists:
                # 当前阶段不支持断点续建；重试时必须清空失败快照遗留的向量，
                # 否则旧点会混入新索引，并导致发布前的双写一致性校验持续失败。
                await asyncio.to_thread(self.client.delete_collection, collection_name=name)
            await asyncio.to_thread(
                self.client.create_collection,
                collection_name=name,
                vectors_config=models.VectorParams(size=vector_size, distance=distance),
            )
        except Exception as exc:  # 统一转换为可重试的基础设施错误。
            raise VectorStoreUnavailableError(f"Qdrant 创建快照集合失败: {exc}") from exc
        return name

    async def upsert(
        self, collection_name: str, chunks: Sequence[Chunk], vectors: Sequence[list[float]]
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        points = [
            models.PointStruct(
                id=chunk.point_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.id,
                    "repo_id": chunk.repo_id,
                    "snapshot_id": chunk.snapshot_id,
                    "commit_sha": chunk.commit_sha,
                    "path": chunk.path,
                    "language": chunk.language,
                    "symbol": chunk.symbol or "",
                    "node_type": chunk.node_type,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content_hash": chunk.content_hash,
                    "is_test": chunk.is_test,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            await asyncio.to_thread(
                self.client.upsert, collection_name=collection_name, points=points, wait=True
            )
        except Exception as exc:  # 统一转换为可重试的基础设施错误。
            raise VectorStoreUnavailableError(f"Qdrant 写入向量失败: {exc}") from exc

    async def validate_snapshot_collection(
        self, collection_name: str, *, expected_points: int, vector_size: int
    ) -> None:
        try:
            info = await asyncio.to_thread(self.client.get_collection, collection_name)
        except Exception as exc:  # 统一转换为可重试的基础设施错误。
            raise VectorStoreUnavailableError(f"Qdrant 快照校验失败: {exc}") from exc
        points_count = int(info.points_count or 0)
        vectors = info.config.params.vectors
        actual_size = getattr(vectors, "size", None)
        if points_count != expected_points:
            raise IndexConsistencyError(
                f"snapshot point count mismatch: expected {expected_points}, got {points_count}"
            )
        if actual_size is None:
            raise IndexConsistencyError("snapshot vector size is unavailable")
        if int(actual_size) != vector_size:
            raise IndexConsistencyError(
                f"snapshot vector size mismatch: expected {vector_size}, got {actual_size}"
            )

    async def snapshot_exists(self, repo_id: str, snapshot_id: str) -> bool:
        try:
            return bool(
                await asyncio.to_thread(
                    self.client.collection_exists, self.collection_name(repo_id, snapshot_id)
                )
            )
        except Exception as exc:  # 就绪检查需要区分缺失集合与连接故障。
            raise VectorStoreUnavailableError(f"Qdrant 快照存在性检查失败: {exc}") from exc

    async def search_snapshot(
        self,
        repo_id: str,
        snapshot_id: str,
        vector: list[float],
        filters: SearchFilter,
        limit: int,
    ) -> list[SearchHit]:
        conditions: list[models.Condition] = []
        if filters.languages:
            conditions.append(
                models.FieldCondition(
                    key="language", match=models.MatchAny(any=list(filters.languages))
                )
            )
        query_filter = models.Filter(must=conditions) if conditions else None
        try:
            response = await asyncio.to_thread(
                self.client.query_points,
                collection_name=self.collection_name(repo_id, snapshot_id),
                query=vector,
                query_filter=query_filter,
                limit=max(limit, limit * 2 if filters.path_prefixes else limit),
                with_payload=True,
            )
        except Exception as exc:  # 查询连接故障应由 API 返回可重试错误。
            raise VectorStoreUnavailableError(f"Qdrant 快照检索失败: {exc}") from exc
        hits: list[SearchHit] = []
        for point in response.points:
            payload = point.payload or {}
            if payload.get("repo_id") != repo_id or payload.get("snapshot_id") != snapshot_id:
                # collection 与 payload 必须指向同一业务快照；发现污染时失败关闭，
                # 不能把其他版本的正文交给生成模型并产生不可追溯引用。
                raise IndexConsistencyError(
                    f"Qdrant payload 与目标快照不一致: {repo_id}/{snapshot_id}"
                )
            path = str(payload.get("path", ""))
            if filters.path_prefixes and not any(
                path.startswith(prefix) for prefix in filters.path_prefixes
            ):
                continue
            hits.append(
                SearchHit(
                    chunk_id=str(payload["chunk_id"]),
                    repo_id=str(payload["repo_id"]),
                    snapshot_id=str(payload["snapshot_id"]),
                    commit_sha=str(payload["commit_sha"]),
                    path=path,
                    start_line=int(payload["start_line"]),
                    end_line=int(payload["end_line"]),
                    score=float(point.score),
                    source="dense",
                    language=str(payload.get("language", "text")),
                    symbol=str(payload.get("symbol") or "") or None,
                    content_hash=str(payload.get("content_hash", "")),
                )
            )
            if len(hits) >= limit:
                break
        return hits
