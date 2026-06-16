from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_key, WorkspaceDep
from api.deps import SecretStoreDep

router = APIRouter(
    prefix="/api/secrets",
    tags=["secrets"],
    dependencies=[Depends(require_api_key)],
)


class SecretCreate(BaseModel):
    name: str
    value: dict[str, Any]  # credential bundle, e.g. {"base_url": "...", "token": "..."}


@router.post("", status_code=201)
async def create_secret(
    body: SecretCreate, secrets: SecretStoreDep, workspace: WorkspaceDep
) -> dict[str, Any]:
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="name must not be empty")
    secret_id = await secrets.put(workspace, body.name, body.value)
    # Never echo the value back.
    return {"id": secret_id, "name": body.name, "workspace_id": workspace}


@router.get("")
async def list_secrets(secrets: SecretStoreDep, workspace: WorkspaceDep) -> list[dict[str, Any]]:
    return await secrets.list_meta(workspace)


@router.delete("/{name}", status_code=204)
async def delete_secret(name: str, secrets: SecretStoreDep, workspace: WorkspaceDep) -> None:
    if not await secrets.delete(workspace, name):
        raise HTTPException(status_code=404, detail="Secret not found")
