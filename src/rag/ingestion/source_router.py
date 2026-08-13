from __future__ import annotations

from rag.domain.errors import InvalidRepositoryError
from rag.domain.models import GitBlob, Repository, SourceType
from rag.ingestion.git_source import LocalGitSource
from rag.ingestion.web_source import WebPageSource


class SourceRouter:
    def __init__(self, git: LocalGitSource, web: WebPageSource) -> None:
        self.git = git
        self.web = web

    def _source(self, repository: Repository) -> LocalGitSource | WebPageSource:
        if repository.source_type in {SourceType.WORKING_TREE, SourceType.LOCAL_MIRROR}:
            return self.git
        if repository.source_type is SourceType.WEB_PAGE:
            return self.web
        raise InvalidRepositoryError(f"unsupported source type: {repository.source_type}")

    async def resolve_ref(self, repository: Repository, ref: str) -> str:
        return await self._source(repository).resolve_ref(repository, ref)

    async def list_blobs(self, repository: Repository, commit_sha: str) -> list[GitBlob]:
        return await self._source(repository).list_blobs(repository, commit_sha)

    async def read_blob(self, repository: Repository, blob_sha: str) -> bytes:
        return await self._source(repository).read_blob(repository, blob_sha)

    async def aclose(self) -> None:
        await self.web.aclose()
