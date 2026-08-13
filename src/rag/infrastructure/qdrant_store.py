from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from rag.domain.models import Chunk, SearchFilter, SearchHit
from rag.infrastructure.settings import QdrantSettings


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)[:120]


class QdrantVectorStore:
    def __init__(self, settings: QdrantSettings) -> None:
        self.settings = settings
        self.client = QdrantClient(url=settings.url, api_key=settings.api_key, timeout=30)

    def alias_name(self, repo_id: str) -> str:
        return _safe_name(self.settings.active_alias_template.format(repo_id=repo_id))

    async def health(self) -> bool:
        try:
            await asyncio.to_thread(self.client.get_collections)
            return True
        except Exception:  # noqa: BLE001 - health probes must convert adapter failures to false
            return False

    async def create_snapshot_collection(
        self, repo_id: str, snapshot_id: str, vector_size: int
    ) -> str:
        name = _safe_name(f"repo_{repo_id}__snap_{snapshot_id}")
        distance = {
            "cosine": models.Distance.COSINE,
            "dot": models.Distance.DOT,
            "euclid": models.Distance.EUCLID,
        }.get(self.settings.distance.lower(), models.Distance.COSINE)
        exists = await asyncio.to_thread(self.client.collection_exists, name)
        if not exists:
            await asyncio.to_thread(
                self.client.create_collection,
                collection_name=name,
                vectors_config=models.VectorParams(size=vector_size, distance=distance),
            )
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
        await asyncio.to_thread(
            self.client.upsert, collection_name=collection_name, points=points, wait=True
        )

    async def activate(self, repo_id: str, collection_name: str) -> None:
        alias = self.alias_name(repo_id)
        aliases = await asyncio.to_thread(self.client.get_aliases)
        operations: list[models.AliasOperations] = []
        if any(item.alias_name == alias for item in aliases.aliases):
            operations.append(
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))
            )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=collection_name, alias_name=alias)
            )
        )
        await asyncio.to_thread(
            self.client.update_collection_aliases, change_aliases_operations=operations
        )

    async def search(
        self,
        repo_id: str,
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
        response = await asyncio.to_thread(
            self.client.query_points,
            collection_name=self.alias_name(repo_id),
            query=vector,
            query_filter=query_filter,
            limit=max(limit, limit * 2 if filters.path_prefixes else limit),
            with_payload=True,
        )
        hits: list[SearchHit] = []
        for point in response.points:
            payload = point.payload or {}
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
