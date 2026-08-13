from __future__ import annotations

import asyncio
import time
from typing import Literal

from rag.domain.errors import NoPublishedSnapshotError
from rag.domain.models import Chunk, QueryResult, SearchFilter, SearchHit
from rag.domain.ports import (
    EmbeddingPort,
    GenerationPort,
    LexicalStorePort,
    MetadataStorePort,
    VectorStorePort,
)
from rag.generation.citation_validator import validate_citations
from rag.generation.prompt_builder import PromptBuilder
from rag.infrastructure.settings import RetrievalSettings
from rag.retrieval.context_builder import build_context
from rag.retrieval.fusion import boost_exact_matches, diversify, reciprocal_rank_fusion


class QueryService:
    def __init__(
        self,
        metadata: MetadataStorePort,
        lexical: LexicalStorePort,
        vectors: VectorStorePort,
        embedding: EmbeddingPort,
        generation: GenerationPort,
        prompt_builder: PromptBuilder,
        settings: RetrievalSettings,
    ) -> None:
        self.metadata = metadata
        self.lexical = lexical
        self.vectors = vectors
        self.embedding = embedding
        self.generation = generation
        self.prompt_builder = prompt_builder
        self.settings = settings

    async def search(
        self,
        question: str,
        filters: SearchFilter,
        final_k: int | None = None,
        mode: Literal["hybrid", "dense", "lexical"] = "hybrid",
    ) -> list[SearchHit]:
        repo_ids = filters.repo_ids or tuple(
            repo.id for repo in await self.metadata.list_repositories()
        )
        snapshots: dict[str, str] = {}
        for repo_id in repo_ids:
            snapshot_id = await self.metadata.get_published_snapshot(repo_id)
            if snapshot_id:
                snapshots[repo_id] = snapshot_id
        if not snapshots:
            raise NoPublishedSnapshotError("no repository has a published snapshot")

        dense_hits: list[SearchHit] = []
        lexical_hits: list[SearchHit] = []
        if mode in {"hybrid", "dense"}:
            vector = await self.embedding.embed_query(question)
            dense_results = await asyncio.gather(
                *[
                    self.vectors.search(repo_id, vector, filters, self.settings.dense_top_k)
                    for repo_id in snapshots
                ]
            )
            dense_hits = [hit for result in dense_results for hit in result]
        if mode in {"hybrid", "lexical"}:
            lexical_hits = await self.lexical.search_lexical(
                question,
                list(snapshots.values()),
                filters,
                self.settings.lexical_top_k,
            )
        ranked_lists = [hits for hits in (dense_hits, lexical_hits) if hits]
        fused = reciprocal_rank_fusion(
            ranked_lists, k=self.settings.rrf_k, limit=self.settings.fused_top_k
        )
        chunk_map = await self.metadata.get_chunks([hit.chunk_id for hit in fused])
        hydrated = [self._hydrate(hit, chunk_map) for hit in fused if hit.chunk_id in chunk_map]
        boosted = boost_exact_matches(
            hydrated,
            question,
            symbol_boost=self.settings.exact_symbol_boost,
            path_boost=self.settings.exact_path_boost,
            class_module_boost=self.settings.class_module_boost,
            declaration_stub_penalty=self.settings.declaration_stub_penalty,
        )
        return diversify(
            boosted,
            final_k=final_k or self.settings.final_top_k,
            max_chunks_per_file=self.settings.max_chunks_per_file,
        )

    async def answer(self, question: str, filters: SearchFilter) -> QueryResult:
        started = time.perf_counter()
        hits = await self.search(question, filters)
        retrieval_finished = time.perf_counter()
        chunks = [self._hit_to_chunk(hit) for hit in hits]
        context, evidence_map = build_context(chunks, self.settings.context_token_budget)
        system_prompt, user_prompt = self.prompt_builder.build(question, context)
        answer = await self.generation.answer(system_prompt, user_prompt)
        answer, citations = validate_citations(answer, evidence_map)
        finished = time.perf_counter()
        confidence = "medium" if citations else "low"
        if not citations:
            answer = "当前索引中没有足够的可验证证据来回答该问题。"
        return QueryResult(
            answer=answer,
            confidence=confidence,
            citations=citations,
            snapshot_ids=tuple(dict.fromkeys(hit.snapshot_id for hit in hits)),
            timing_ms={
                "retrieval": round((retrieval_finished - started) * 1000),
                "generation": round((finished - retrieval_finished) * 1000),
                "total": round((finished - started) * 1000),
            },
        )

    @staticmethod
    def _hydrate(hit: SearchHit, chunks: dict[str, Chunk]) -> SearchHit:
        chunk = chunks[hit.chunk_id]
        return SearchHit(
            chunk_id=hit.chunk_id,
            repo_id=chunk.repo_id,
            snapshot_id=chunk.snapshot_id,
            commit_sha=chunk.commit_sha,
            path=chunk.path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            score=hit.score,
            source=hit.source,
            language=chunk.language,
            symbol=chunk.symbol,
            content=chunk.content,
            content_hash=chunk.content_hash,
            metadata=chunk.metadata,
        )

    @staticmethod
    def _hit_to_chunk(hit: SearchHit) -> Chunk:
        return Chunk(
            id=hit.chunk_id,
            point_id="",
            repo_id=hit.repo_id,
            snapshot_id=hit.snapshot_id,
            commit_sha=hit.commit_sha,
            path=hit.path,
            language=hit.language,
            content=hit.content,
            embedding_text=hit.content,
            content_hash=hit.content_hash,
            start_line=hit.start_line,
            end_line=hit.end_line,
            symbol=hit.symbol,
        )
