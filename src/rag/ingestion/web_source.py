from __future__ import annotations

import hashlib
import ipaddress
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from rag.domain.errors import InvalidRepositoryError
from rag.domain.models import GitBlob, Repository, SourceType
from rag.infrastructure.settings import IngestionSettings

_IGNORED_TAGS = {"script", "style", "nav", "header", "footer", "aside", "svg", "form"}
_BLOCK_TAGS = {"p", "div", "section", "article", "blockquote", "table", "tr"}


class _MarkdownExtractor(HTMLParser):
    def __init__(self, *, main_only: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.main_only = main_only
        self.main_depth = 0
        self.ignored_depth = 0
        self.pre_depth = 0
        self.parts: list[str] = []

    @property
    def active(self) -> bool:
        return not self.main_only or self.main_depth > 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "main":
            self.main_depth += 1
        if not self.active:
            return
        if tag in _IGNORED_TAGS:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.parts.append(f"\n\n{'#' * int(tag[1])} ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "pre":
            self.pre_depth += 1
            self.parts.append("\n\n```\n")
        elif tag == "code" and not self.pre_depth:
            self.parts.append("`")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        was_active = self.active
        if was_active and tag in _IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
        elif was_active and not self.ignored_depth:
            if tag == "pre" and self.pre_depth:
                self.pre_depth -= 1
                self.parts.append("\n```\n")
            elif tag == "code" and not self.pre_depth:
                self.parts.append("`")
            elif tag in _BLOCK_TAGS or tag == "li" or re.fullmatch(r"h[1-6]", tag):
                self.parts.append("\n")
        if tag == "main" and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.active or self.ignored_depth:
            return
        if self.pre_depth:
            self.parts.append(data)
            return
        normalized = re.sub(r"\s+", " ", data)
        if normalized.strip():
            self.parts.append(normalized)

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    main = _MarkdownExtractor(main_only=True)
    main.feed(html)
    content = main.markdown()
    if content:
        return content
    fallback = _MarkdownExtractor(main_only=False)
    fallback.feed(html)
    return fallback.markdown()


class WebPageSource:
    def __init__(self, settings: IngestionSettings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=settings.web_request_timeout_seconds,
            headers={"User-Agent": "Local-RAG/0.1 (+single-page knowledge source)"},
        )
        self._documents: dict[str, bytes] = {}

    async def resolve_ref(self, repository: Repository, ref: str) -> str:
        del ref
        self._validate(repository)
        url = repository.source_uri
        response: httpx.Response | None = None
        for _ in range(6):
            self._validate_url(url)
            response = await self.client.get(url)
            if not response.is_redirect:
                break
            location = response.headers.get("location")
            if not location:
                raise InvalidRepositoryError("web source redirect has no location")
            url = str(response.url.join(location))
        else:
            raise InvalidRepositoryError("web source has too many redirects")
        assert response is not None
        response.raise_for_status()
        self._validate_url(str(response.url))
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            raise InvalidRepositoryError(f"web source is not HTML: {content_type or 'unknown'}")
        raw = response.content
        if len(raw) > self.settings.max_file_bytes:
            raise InvalidRepositoryError("web source exceeds ingestion.max_file_bytes")
        markdown = html_to_markdown(response.text)
        if not markdown:
            raise InvalidRepositoryError("web source produced no readable main content")
        document = (markdown + "\n").encode("utf-8")
        digest = hashlib.sha256(document).hexdigest()
        self._documents[digest] = document
        return digest

    async def list_blobs(self, repository: Repository, commit_sha: str) -> list[GitBlob]:
        document = self._documents.get(commit_sha)
        if document is None:
            raise InvalidRepositoryError("web source content is not loaded")
        return [GitBlob(path=repository.source_uri, blob_sha=commit_sha, size=len(document))]

    async def read_blob(self, repository: Repository, blob_sha: str) -> bytes:
        del repository
        document = self._documents.get(blob_sha)
        if document is None:
            raise InvalidRepositoryError("web source content is not loaded")
        return document

    async def aclose(self) -> None:
        await self.client.aclose()

    def _validate(self, repository: Repository) -> None:
        if repository.source_type is not SourceType.WEB_PAGE:
            raise InvalidRepositoryError("source is not a web page")
        self._validate_url(repository.source_uri)

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname:
            raise InvalidRepositoryError("web source must use an HTTPS URL")
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise InvalidRepositoryError("IP-address web sources are not allowed")
        allowed = {host.lower() for host in self.settings.web_allowed_hosts}
        if hostname not in allowed:
            raise InvalidRepositoryError(f"web source host is not allowed: {hostname}")
