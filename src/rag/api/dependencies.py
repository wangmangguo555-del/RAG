from __future__ import annotations

import secrets
from typing import cast

from fastapi import Header, HTTPException, Request, status

from rag.container import Container


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


async def require_admin(request: Request, authorization: str | None = Header(default=None)) -> None:
    container = get_container(request)
    expected = container.settings.security.admin_token
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
