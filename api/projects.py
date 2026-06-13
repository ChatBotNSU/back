from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_key, WorkspaceDep
from api.deps import ProjectStoreDep
from stores.project_store import Project, new_project

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_api_key)])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    metadata: dict[str, Any] = {}


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


def _to_response(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=p.id, workspace_id=p.workspace_id, name=p.name, description=p.description,
        metadata=p.metadata, created_at=p.created_at, updated_at=p.updated_at,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(projects: ProjectStoreDep, workspace: WorkspaceDep) -> list[ProjectResponse]:
    return [_to_response(p) for p in await projects.list_all(workspace_id=workspace)]


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate, projects: ProjectStoreDep, workspace: WorkspaceDep
) -> ProjectResponse:
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="name must not be empty")
    project = new_project(workspace, body.name, body.description)
    project.metadata = body.metadata
    await projects.save(project)
    return _to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str, projects: ProjectStoreDep, workspace: WorkspaceDep
) -> ProjectResponse:
    project = await projects.get(project_id, workspace_id=workspace)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_response(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str, body: ProjectUpdate, projects: ProjectStoreDep, workspace: WorkspaceDep
) -> ProjectResponse:
    project = await projects.get(project_id, workspace_id=workspace)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.metadata is not None:
        project.metadata = body.metadata
    await projects.save(project)
    return _to_response(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str, projects: ProjectStoreDep, workspace: WorkspaceDep
) -> None:
    project = await projects.get(project_id, workspace_id=workspace)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await projects.delete(project_id, workspace_id=workspace)
