from __future__ import annotations

import hashlib
from collections.abc import Sequence

from rag.domain.errors import RepositoryNotFoundError
from rag.domain.models import Chunk, GitBlob, Repository, SourceDocument, SourceType
from rag.domain.ports import EmbeddingPort, GitSourcePort, MetadataStorePort, VectorStorePort
from rag.infrastructure.settings import IngestionSettings
from rag.ingestion.chunkers.structured import ChunkingOptions, StructuredChunker
from rag.ingestion.discovery import (
    contains_secret,
    decode_text,
    detect_language,
    filter_blobs,
)


class IndexService:
    def __init__(
        self,
        metadata: MetadataStorePort,
        git: GitSourcePort,
        embedding: EmbeddingPort,
        vectors: VectorStorePort,
        settings: IngestionSettings,
        embedding_fingerprint: str,
        redact_secrets: bool = True,
    ) -> None:
        self.metadata = metadata
        self.git = git
        self.embedding = embedding
        self.vectors = vectors
        self.settings = settings
        self.embedding_fingerprint = embedding_fingerprint
        self.redact_secrets = redact_secrets
        self.chunker = StructuredChunker(
            ChunkingOptions(
                target_tokens=settings.chunk_target_tokens,
                max_tokens=settings.chunk_max_tokens,
                min_tokens=settings.chunk_min_tokens,
                overlap_tokens=settings.text_overlap_tokens,
                version=settings.chunker_version,
            )
        )

    async def submit(self, repo_id: str, ref: str | None = None) -> str:
        repository = await self.metadata.get_repository(repo_id)
        if not repository:
            raise RepositoryNotFoundError(repo_id)
        return await self.metadata.create_job(repo_id, ref or repository.default_ref)

    async def execute_job(self, job_id: str) -> dict[str, int]:
        job = await self.metadata.get_job(job_id)
        if not job:
            raise ValueError(f"job not found: {job_id}")
        repository = await self.metadata.get_repository(job.repo_id)
        if not repository:
            raise RepositoryNotFoundError(job.repo_id)

        commit = await self.git.resolve_ref(repository, job.requested_ref)
        index_version = hashlib.sha256(
            f"{self.embedding_fingerprint}|{self.settings.chunker_version}".encode()
        ).hexdigest()[:16]
        existing_snapshot = await self.metadata.find_published_snapshot(
            repository.id, commit, index_version
        )
        if existing_snapshot:
            stats = {"files": 0, "chunks": 0, "skipped": 0, "reused_snapshot": 1}
            await self.metadata.complete_job(job_id, success=True, commit_sha=commit)
            return stats
        snapshot_id = await self.metadata.create_snapshot(repository.id, commit, index_version)
        collection_name: str | None = None
        stats = {"files": 0, "chunks": 0, "skipped": 0}
        try:
            all_blobs = await self.git.list_blobs(repository, commit)
            ragignore_lines = await self._load_ragignore(repository, all_blobs)
            blobs = filter_blobs(
                all_blobs,
                repository,
                self.settings.max_file_bytes,
                ragignore_lines,
            )
            pending_chunks: list[Chunk] = []
            vector_size: int | None = None
            for blob in blobs:
                raw = await self.git.read_blob(repository, blob.blob_sha)
                content = decode_text(raw)
                if content is None or (self.redact_secrets and contains_secret(content)):
                    stats["skipped"] += 1
                    continue
                language = (
                    "markdown"
                    if repository.source_type is SourceType.WEB_PAGE
                    else detect_language(blob.path)
                )
                document = SourceDocument(
                    repo_id=repository.id,
                    commit_sha=commit,
                    path=blob.path,
                    blob_sha=blob.blob_sha,
                    language=language,
                    content=content,
                )
                chunks = self.chunker.chunk(document, snapshot_id)
                await self.metadata.save_file(
                    snapshot_id,
                    path=blob.path,
                    blob_sha=blob.blob_sha,
                    language=language,
                    parse_status="fallback",
                    content_bytes=len(raw),
                )
                pending_chunks.extend(chunks)
                stats["files"] += 1
                if len(pending_chunks) >= self.settings.embedding_batch_size:
                    collection_name, vector_size = await self._flush(
                        repository.id,
                        snapshot_id,
                        pending_chunks,
                        collection_name,
                        vector_size,
                    )
                    stats["chunks"] += len(pending_chunks)
                    pending_chunks = []
            if pending_chunks:
                collection_name, vector_size = await self._flush(
                    repository.id,
                    snapshot_id,
                    pending_chunks,
                    collection_name,
                    vector_size,
                )
                stats["chunks"] += len(pending_chunks)
            if not collection_name:
                raise ValueError("repository produced no indexable chunks")
            await self.vectors.activate(repository.id, collection_name)
            await self.metadata.publish_snapshot(snapshot_id, stats)
            await self.metadata.complete_job(job_id, success=True, commit_sha=commit)
            return stats
        except Exception as exc:
            await self.metadata.fail_snapshot(snapshot_id, str(exc))
            await self.metadata.complete_job(
                job_id,
                success=False,
                commit_sha=commit,
                error_code=getattr(exc, "code", "INDEXING_ERROR"),
                error_message=str(exc),
            )
            raise

    async def _load_ragignore(
        self, repository: Repository, blobs: Sequence[GitBlob]
    ) -> tuple[str, ...]:
        ignore_blob = next((blob for blob in blobs if blob.path == ".ragignore"), None)
        if not ignore_blob:
            return ()
        content = decode_text(await self.git.read_blob(repository, ignore_blob.blob_sha))
        if content is None:
            return ()
        return tuple(
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

    async def _flush(
        self,
        repo_id: str,
        snapshot_id: str,
        chunks: Sequence[Chunk],
        collection_name: str | None,
        vector_size: int | None,
    ) -> tuple[str, int]:
        vectors = await self.embedding.embed_documents([chunk.embedding_text for chunk in chunks])
        if not vectors:
            raise ValueError("embedding service returned no vectors")
        dimension = len(vectors[0])
        if vector_size is not None and dimension != vector_size:
            raise ValueError("embedding dimension changed during indexing")
        if collection_name is None:
            collection_name = await self.vectors.create_snapshot_collection(
                repo_id, snapshot_id, dimension
            )
        await self.vectors.upsert(collection_name, chunks, vectors)
        await self.metadata.save_chunks(chunks)
        return collection_name, dimension
