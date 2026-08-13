from rag.domain.models import Chunk
from rag.generation.citation_validator import validate_citations


def test_only_known_citations_are_mapped() -> None:
    chunk = Chunk(
        id="c1",
        point_id="p1",
        repo_id="demo",
        snapshot_id="s1",
        commit_sha="a" * 40,
        path="README.md",
        language="markdown",
        content="supported fact",
        embedding_text="supported fact",
        content_hash="h1",
        start_line=1,
        end_line=2,
    )
    answer, citations = validate_citations("Fact [E1], invented [E9].", {"E1": chunk})
    assert answer.startswith("Fact")
    assert [citation.id for citation in citations] == ["E1"]
