from dataclasses import replace

from rag.domain.models import SearchHit
from rag.retrieval.fusion import boost_exact_matches, diversify, reciprocal_rank_fusion


def _hit(chunk_id: str, path: str, source: str) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        repo_id="demo",
        snapshot_id="s1",
        commit_sha="a" * 40,
        path=path,
        start_line=1,
        end_line=2,
        score=1,
        source=source,
        content_hash=chunk_id,
    )


def test_rrf_rewards_hits_present_in_both_lists() -> None:
    fused = reciprocal_rank_fusion(
        [
            [_hit("a", "a.py", "dense"), _hit("b", "b.py", "dense")],
            [_hit("b", "b.py", "lexical"), _hit("c", "c.py", "lexical")],
        ],
        k=60,
        limit=3,
    )
    assert fused[0].chunk_id == "b"
    assert fused[0].source == "dense+lexical"


def test_diversify_limits_per_file() -> None:
    selected = diversify(
        [_hit("a", "one.py", "dense"), _hit("b", "one.py", "dense"), _hit("c", "two.py", "dense")],
        final_k=3,
        max_chunks_per_file=1,
    )
    assert [hit.chunk_id for hit in selected] == ["a", "c"]


def test_exact_symbol_and_path_matches_are_boosted() -> None:
    symbol_hit = _hit("symbol", "src/service.py", "dense")
    symbol_hit = replace(symbol_hit, symbol="QueryService")
    path_hit = _hit("path", "config/default.yaml", "dense")
    unrelated = _hit("other", "README.md", "dense")

    boosted = boost_exact_matches(
        [unrelated, path_hit, symbol_hit],
        "QueryService 如何读取 default.yaml？",
        symbol_boost=0.02,
        path_boost=0.01,
    )

    assert [hit.chunk_id for hit in boosted] == ["symbol", "path", "other"]


def test_plain_words_do_not_trigger_symbol_boost() -> None:
    chunk_hit = replace(_hit("chunk", "src/models.py", "dense"), symbol="Chunk")
    first = _hit("first", "README.md", "dense")

    boosted = boost_exact_matches(
        [first, chunk_hit],
        "如何限制同一个文件的 chunk 数量？",
        symbol_boost=0.02,
        path_boost=0.01,
    )

    assert [hit.chunk_id for hit in boosted] == ["first", "chunk"]


def test_class_query_prefers_implementation_over_declaration_stub() -> None:
    declaration = replace(
        _hit("declaration", "src/rag/application/index_service.py", "dense"),
        symbol="IndexService",
        content="class IndexService:",
        score=0.02,
    )
    implementation = replace(
        _hit("implementation", "src/rag/application/index_service.py", "lexical"),
        symbol="submit",
        content=(
            "async def submit(self, repo_id: str) -> str:\n"
            "    repository = await self.metadata.get_repository(repo_id)\n"
            "    return repository.id"
        ),
        score=0.02,
    )
    unrelated = replace(_hit("other", "README.md", "dense"), score=0.03)

    boosted = boost_exact_matches(
        [declaration, unrelated, implementation],
        "IndexService 如何提交任务？",
        symbol_boost=0.02,
        path_boost=0.01,
        class_module_boost=0.02,
        declaration_stub_penalty=0.02,
    )

    assert boosted[0].chunk_id == "implementation"
    assert boosted[-1].chunk_id == "declaration"
