from pathlib import Path

import httpx
import pytest

from rag.api.app import create_app
from rag.container import Container
from rag.domain.models import Repository, SourceType
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


@pytest.mark.asyncio
async def test_ready_fails_when_published_snapshot_collection_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    settings = Settings(
        sqlite=SqliteSettings(path=tmp_path / "rag.db", migrations_dir=project_root / "migrations")
    )
    container = Container.build(settings, project_root)

    async def available() -> bool:
        return True

    async def missing(repo_id: str, snapshot_id: str) -> bool:
        del repo_id, snapshot_id
        return False

    monkeypatch.setattr(container.vectors, "health", available)
    monkeypatch.setattr(container.vectors, "snapshot_exists", missing)
    monkeypatch.setattr(container.embeddings, "health", available)
    monkeypatch.setattr(container.generation, "health", available)
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        await container.metadata.register_repository(
            Repository("demo", "Demo", SourceType.WORKING_TREE, str(tmp_path), "HEAD")
        )
        snapshot_id = await container.metadata.create_snapshot("demo", "a" * 40, "v1")
        await container.metadata.publish_snapshot(snapshot_id, {"files": 1, "chunks": 1})
        response = await client.get("/health/ready")
    await container.close()

    assert response.status_code == 503
    assert response.json()["checks"]["published_snapshots"] is False
