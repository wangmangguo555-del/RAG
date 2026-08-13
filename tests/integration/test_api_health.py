from pathlib import Path

import httpx
import pytest

from rag.api.app import create_app
from rag.container import Container
from rag.infrastructure.settings import Settings, SqliteSettings


@pytest.mark.asyncio
async def test_live_endpoint(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    settings = Settings(
        sqlite=SqliteSettings(path=tmp_path / "rag.db", migrations_dir=project_root / "migrations")
    )
    container = Container.build(settings, project_root)
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.get("/health/live")
    await container.close()
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
