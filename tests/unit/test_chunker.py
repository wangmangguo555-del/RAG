from rag.domain.models import SourceDocument
from rag.ingestion.chunkers.structured import ChunkingOptions, StructuredChunker


def test_chunk_ids_are_deterministic_and_lines_are_preserved() -> None:
    document = SourceDocument(
        repo_id="demo",
        commit_sha="a" * 40,
        path="src/service.py",
        blob_sha="b" * 40,
        language="python",
        content="class Service:\n    pass\n\ndef run():\n    return 1\n",
    )
    chunker = StructuredChunker(ChunkingOptions(max_tokens=900))

    first = chunker.chunk(document, "snapshot-1")
    second = chunker.chunk(document, "snapshot-1")

    assert first
    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert first[0].start_line == 1
    assert first[-1].end_line == 5
    assert all(chunk.point_id for chunk in first)


def test_markdown_splits_on_headings() -> None:
    document = SourceDocument(
        repo_id="demo",
        commit_sha="a" * 40,
        path="README.md",
        blob_sha="b" * 40,
        language="markdown",
        content="# Intro\nhello\n## Usage\nrun it\n",
    )
    chunks = StructuredChunker(ChunkingOptions()).chunk(document, "snapshot-1")
    assert [chunk.symbol for chunk in chunks] == ["Intro", "Usage"]
    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(1, 2), (3, 4)]
