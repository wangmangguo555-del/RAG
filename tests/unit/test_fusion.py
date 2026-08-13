from rag.domain.models import SearchHit
from rag.retrieval.fusion import diversify, reciprocal_rank_fusion


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
