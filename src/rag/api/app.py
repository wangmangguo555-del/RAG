from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, ORJSONResponse

from rag.api import admin_routes, query_routes
from rag.api.schemas import ErrorBody, ErrorResponse, HealthResponse
from rag.container import Container
from rag.domain.errors import RagError
from rag.infrastructure.settings import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _container_from_environment() -> Container:
    config_path = os.getenv("RAG_CONFIG", str(PROJECT_ROOT / "config" / "default.yaml"))
    return Container.build(load_settings(config_path), PROJECT_ROOT)


def create_app(container: Container | None = None) -> FastAPI:
    owned_container = container is None
    app_container = container or _container_from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app_container.metadata.initialize()
        app.state.container = app_container
        yield
        if owned_container:
            await app_container.close()

    app = FastAPI(
        title="Local RAG",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        structlog.get_logger().info(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return response

    @app.exception_handler(RagError)
    async def rag_error_handler(request: Request, exc: RagError) -> ORJSONResponse:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        body = ErrorResponse(
            error=ErrorBody(
                code=exc.code,
                message=str(exc),
                request_id=request_id,
                retryable=exc.retryable,
            )
        )
        return ORJSONResponse(status_code=503 if exc.retryable else 400, content=body.model_dump())

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready() -> JSONResponse:
        checks = {
            "sqlite": await app_container.metadata.health(),
            "qdrant": await app_container.vectors.health(),
            "llm": await app_container.generation.health(),
            "embedding": await app_container.embeddings.health(),
        }
        ready_status = all(checks.values())
        return JSONResponse(
            status_code=200 if ready_status else 503,
            content=HealthResponse(
                status="ok" if ready_status else "not_ready", checks=checks
            ).model_dump(),
        )

    app.include_router(query_routes.router, prefix="/api/v1")
    app.include_router(admin_routes.router, prefix="/api/v1/admin")
    return app


app = create_app()
