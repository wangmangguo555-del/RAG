from __future__ import annotations

import asyncio
import os
from pathlib import Path

from rag.domain.errors import InvalidRepositoryError
from rag.domain.models import GitBlob, Repository, SourceType


class LocalGitSource:
    async def resolve_ref(self, repository: Repository, ref: str) -> str:
        self._validate(repository)
        output = await self._run(repository, "rev-parse", f"{ref}^{{commit}}")
        commit = output.decode("ascii", errors="strict").strip()
        if len(commit) != 40:
            raise InvalidRepositoryError(f"unexpected commit SHA for {repository.id}")
        return commit

    async def list_blobs(self, repository: Repository, commit_sha: str) -> list[GitBlob]:
        output = await self._run(repository, "ls-tree", "-r", "-z", "--long", commit_sha)
        blobs: list[GitBlob] = []
        for record in output.split(b"\0"):
            if not record:
                continue
            metadata, path_bytes = record.split(b"\t", 1)
            _mode, object_type, sha, size = metadata.split(b" ", 3)
            if object_type != b"blob":
                continue
            blobs.append(
                GitBlob(
                    path=path_bytes.decode("utf-8", errors="surrogateescape").replace("\\", "/"),
                    blob_sha=sha.decode("ascii"),
                    size=int(size),
                )
            )
        return blobs

    async def read_blob(self, repository: Repository, blob_sha: str) -> bytes:
        return await self._run(repository, "cat-file", "blob", blob_sha)

    @staticmethod
    def _validate(repository: Repository) -> None:
        if repository.source_type not in {SourceType.WORKING_TREE, SourceType.LOCAL_MIRROR}:
            raise InvalidRepositoryError("only local Git sources are enabled")
        path = Path(repository.source_uri).resolve()
        if not path.exists():
            raise InvalidRepositoryError(f"repository path does not exist: {path}")

    async def _run(self, repository: Repository, *arguments: str) -> bytes:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(Path(repository.source_uri).resolve()),
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise InvalidRepositoryError(f"git command failed: {message[:1000]}")
        return stdout
