from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from config import DEFAULT_WORKSPACE, settings
from services.security import decode_token


@dataclass
class Identity:
    workspace_id: str
    user_id: str | None = None


def _resolve_identity(request: Request) -> Identity | None:
    """Resolve the caller from a Bearer JWT, an X-API-Key, or dev mode."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_token(auth[7:])
        if payload and payload.get("ws"):
            return Identity(workspace_id=str(payload["ws"]), user_id=payload.get("sub"))
        return None  # a malformed/expired token is an explicit failure

    key = request.headers.get("X-API-Key", "")
    if settings._entries():  # API keys configured → require a valid one
        if settings.is_valid_api_key(key):
            return Identity(workspace_id=settings.workspace_for_key(key))
        return None
    return Identity(workspace_id=DEFAULT_WORKSPACE)  # dev mode: auth disabled


async def require_auth(request: Request) -> Identity:
    identity = _resolve_identity(request)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity


# Backwards-compatible alias: routers use this as their auth gate.
require_api_key = require_auth

IdentityDep = Annotated[Identity, Depends(require_auth)]


async def current_workspace(identity: IdentityDep) -> str:
    return identity.workspace_id


WorkspaceDep = Annotated[str, Depends(current_workspace)]
