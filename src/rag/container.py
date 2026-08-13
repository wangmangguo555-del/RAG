from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rag.application.index_service import IndexService
from rag.application.query_service import QueryService
from rag.generation.prompt_builder import PromptBuilder
from rag.infrastructure.llama_client import LlamaEmbeddingClient, LlamaGenerationClient
from rag.infrastructure.qdrant_store import QdrantVectorStore
from rag.infrastructure.settings import Settings
from rag.infrastructure.sqlite_store import SqliteStore
from rag.ingestion.git_source import LocalGitSource
from rag.ingestion.source_router import SourceRouter
from rag.ingestion.web_source import WebPageSource


@dataclass(slots=True)
class Container:
    settings: Settings
    metadata: SqliteStore
    embeddings: LlamaEmbeddingClient
    generation: LlamaGenerationClient
    vectors: QdrantVectorStore
    sources: SourceRouter
    index_service: IndexService
    query_service: QueryService

    @classmethod
    def build(cls, settings: Settings, project_root: Path) -> Container:
        metadata = SqliteStore(settings.sqlite)
        embeddings = LlamaEmbeddingClient(settings.embedding)
        generation = LlamaGenerationClient(settings.llm)
        vectors = QdrantVectorStore(settings.qdrant)
        sources = SourceRouter(LocalGitSource(), WebPageSource(settings.ingestion))
        index_service = IndexService(
            metadata=metadata,
            git=sources,
            embedding=embeddings,
            vectors=vectors,
            settings=settings.ingestion,
            embedding_fingerprint=settings.embedding.fingerprint,
            redact_secrets=settings.security.redact_secrets,
        )
        query_service = QueryService(
            metadata=metadata,
            lexical=metadata,
            vectors=vectors,
            embedding=embeddings,
            generation=generation,
            prompt_builder=PromptBuilder(project_root / "prompts"),
            settings=settings.retrieval,
        )
        return cls(
            settings=settings,
            metadata=metadata,
            embeddings=embeddings,
            generation=generation,
            vectors=vectors,
            sources=sources,
            index_service=index_service,
            query_service=query_service,
        )

    async def close(self) -> None:
        await self.sources.aclose()
        await self.embeddings.aclose()
        await self.generation.aclose()
