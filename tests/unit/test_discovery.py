from rag.domain.models import GitBlob, Repository, SourceType
from rag.ingestion.discovery import filter_blobs


def test_ragignore_excludes_repository_paths() -> None:
    repository = Repository("demo", "Demo", SourceType.WORKING_TREE, ".")
    blobs = [
        GitBlob("src/main.py", "a" * 40, 10),
        GitBlob("generated/client.py", "b" * 40, 10),
    ]
    selected = filter_blobs(blobs, repository, 1024, ("generated/",))
    assert [blob.path for blob in selected] == ["src/main.py"]
