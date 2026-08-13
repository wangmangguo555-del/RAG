import httpx
import pytest

from rag.domain.errors import InvalidRepositoryError, SourceUnavailableError
from rag.domain.models import Repository, SourceType
from rag.infrastructure.settings import IngestionSettings
from rag.ingestion.web_source import WebPageSource, html_to_markdown


def test_html_to_markdown_prefers_main_content() -> None:
    html = """
    <html><body><nav>Navigation</nav><main>
      <h1>Vue 简介</h1><p>用于构建用户界面的框架。</p>
      <h2>示例</h2><pre><code>createApp({})</code></pre>
    </main><footer>Footer</footer></body></html>
    """
    markdown = html_to_markdown(html)
    assert "# Vue 简介" in markdown
    assert "用于构建用户界面的框架。" in markdown
    assert "createApp({})" in markdown
    assert "Navigation" not in markdown
    assert "Footer" not in markdown


@pytest.mark.asyncio
async def test_web_source_rejects_unlisted_host() -> None:
    source = WebPageSource(IngestionSettings(web_allowed_hosts=("cn.vuejs.org",)))
    repository = Repository(
        "example",
        "Example",
        SourceType.WEB_PAGE,
        "https://example.com/guide.html",
        "live",
    )
    try:
        with pytest.raises(InvalidRepositoryError, match="not allowed"):
            await source.resolve_ref(repository, "live")
    finally:
        await source.aclose()


@pytest.mark.asyncio
async def test_web_source_exposes_cleaned_page_as_blob() -> None:
    source = WebPageSource(IngestionSettings(web_allowed_hosts=("cn.vuejs.org",)))

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<main><h1>简介</h1><p>Vue 是渐进式框架。</p></main>",
            request=request,
        )

    await source.client.aclose()
    source.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    repository = Repository(
        "vue-guide",
        "Vue 中文指南",
        SourceType.WEB_PAGE,
        "https://cn.vuejs.org/guide/introduction.html",
        "live",
    )
    try:
        version = await source.resolve_ref(repository, "live")
        blobs = await source.list_blobs(repository, version)
        content = await source.read_blob(repository, blobs[0].blob_sha)
    finally:
        await source.aclose()
    assert len(version) == 64
    assert blobs[0].path == repository.source_uri
    assert "Vue 是渐进式框架。" in content.decode()


@pytest.mark.asyncio
async def test_web_source_marks_server_error_as_retryable() -> None:
    source = WebPageSource(IngestionSettings(web_allowed_hosts=("docs.example.com",)))

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    await source.client.aclose()
    source.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    repository = Repository(
        "docs",
        "Docs",
        SourceType.WEB_PAGE,
        "https://docs.example.com/guide",
        "live",
    )
    try:
        with pytest.raises(SourceUnavailableError) as error:
            await source.resolve_ref(repository, "live")
    finally:
        await source.aclose()
    assert error.value.retryable is True
