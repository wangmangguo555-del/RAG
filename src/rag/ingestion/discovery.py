from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath

from pathspec import PathSpec

from rag.domain.models import GitBlob, Repository

DEFAULT_EXCLUDES = (
    ".git/**",
    "**/node_modules/**",
    "**/vendor/**",
    "**/dist/**",
    "**/build/**",
    "**/target/**",
    "**/.venv/**",
    "**/__pycache__/**",
    "**/coverage/**",
    "**/*.min.js",
    "**/*.map",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.pdf",
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
    "**/*.exe",
    "**/*.dll",
    "**/*.so",
    "**/*.dylib",
    "**/*.class",
    "**/*.jar",
    "**/.env",
    "**/.env.*",
    "**/*.pem",
    "**/*.key",
)

TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".mdx",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{20,}"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
)


def filter_blobs(
    blobs: list[GitBlob],
    repository: Repository,
    max_file_bytes: int,
    ragignore_lines: tuple[str, ...] = (),
) -> list[GitBlob]:
    excludes = PathSpec.from_lines(
        "gitwildmatch", (*DEFAULT_EXCLUDES, *repository.exclude, *ragignore_lines)
    )
    selected: list[GitBlob] = []
    for blob in blobs:
        path = blob.path
        suffix = PurePosixPath(path).suffix.lower()
        if blob.size <= 0 or blob.size > max_file_bytes:
            continue
        if excludes.match_file(path):
            continue
        if repository.include and not any(
            fnmatch.fnmatch(path, rule) for rule in repository.include
        ):
            continue
        if suffix not in TEXT_EXTENSIONS and PurePosixPath(path).name.lower() not in {
            "dockerfile",
            "makefile",
            "readme",
            "license",
        }:
            continue
        selected.append(blob)
    return selected


def decode_text(raw: bytes) -> str | None:
    if b"\x00" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def contains_secret(text: str) -> bool:
    sample = text[:200_000]
    return any(pattern.search(sample) for pattern in SECRET_PATTERNS)


LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".html": "html",
    ".md": "markdown",
    ".mdx": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".sql": "sql",
    ".sh": "shell",
}


def detect_language(path: str) -> str:
    return LANGUAGES.get(PurePosixPath(path).suffix.lower(), "text")
