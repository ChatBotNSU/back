from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_key, WorkspaceDep
from api.deps import IntegrationStoreDep, ProjectStoreDep

router = APIRouter(prefix="/api/projects", tags=["integrations"], dependencies=[Depends(require_api_key)])

_KINDS = {"provider", "http", "db"}


class IntegrationBody(BaseModel):
    name: str
    kind: str = "provider"
    config: dict[str, Any] = {}


async def _check_project(projects: ProjectStoreDep, project_id: str, workspace: str) -> None:
    if await projects.get(project_id, workspace_id=workspace) is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{project_id}/integrations")
async def list_integrations(
    project_id: str, integrations: IntegrationStoreDep,
    projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> list[dict[str, Any]]:
    await _check_project(projects, project_id, workspace)
    return [i.to_dict() for i in await integrations.list_all(project_id)]


@router.post("/{project_id}/integrations", status_code=201)
async def upsert_integration(
    project_id: str, body: IntegrationBody, integrations: IntegrationStoreDep,
    projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> dict[str, Any]:
    await _check_project(projects, project_id, workspace)
    if body.kind not in _KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {sorted(_KINDS)}")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="name must not be empty")
    integ = await integrations.put(project_id, body.name, body.kind, body.config)
    return integ.to_dict()


@router.delete("/{project_id}/integrations/{name}", status_code=204)
async def delete_integration(
    project_id: str, name: str, integrations: IntegrationStoreDep,
    projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> None:
    await _check_project(projects, project_id, workspace)
    if not await integrations.delete(project_id, name):
        raise HTTPException(status_code=404, detail="Integration not found")
