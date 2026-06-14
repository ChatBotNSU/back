from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_key, WorkspaceDep
from api.deps import DataStoreDep, ProjectStoreDep

router = APIRouter(prefix="/api/projects", tags=["data"], dependencies=[Depends(require_api_key)])


class RecordBody(BaseModel):
    data: dict[str, Any]


class QueryBody(BaseModel):
    where: dict[str, Any] = {}
    limit: int = 100


async def _check_project(projects: ProjectStoreDep, project_id: str, workspace: str) -> None:
    if await projects.get(project_id, workspace_id=workspace) is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{project_id}/tables")
async def list_tables(
    project_id: str, data: DataStoreDep, projects: ProjectStoreDep, workspace: WorkspaceDep
) -> dict[str, Any]:
    await _check_project(projects, project_id, workspace)
    return {"tables": await data.list_tables(project_id)}


@router.post("/{project_id}/tables/{table}/records", status_code=201)
async def insert_record(
    project_id: str, table: str, body: RecordBody,
    data: DataStoreDep, projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> dict[str, Any]:
    await _check_project(projects, project_id, workspace)
    rec = await data.insert(project_id, table, body.data)
    return rec.to_dict()


@router.get("/{project_id}/tables/{table}/records")
async def list_records(
    project_id: str, table: str,
    data: DataStoreDep, projects: ProjectStoreDep, workspace: WorkspaceDep,
    limit: int = 100,
) -> dict[str, Any]:
    await _check_project(projects, project_id, workspace)
    recs = await data.query(project_id, table, {}, limit=limit)
    return {"records": [r.to_dict() for r in recs], "count": len(recs)}


@router.post("/{project_id}/tables/{table}/records/query")
async def query_records(
    project_id: str, table: str, body: QueryBody,
    data: DataStoreDep, projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> dict[str, Any]:
    await _check_project(projects, project_id, workspace)
    recs = await data.query(project_id, table, body.where, limit=body.limit)
    return {"records": [r.to_dict() for r in recs], "count": len(recs)}


@router.get("/{project_id}/tables/{table}/records/{record_id}")
async def get_record(
    project_id: str, table: str, record_id: str,
    data: DataStoreDep, projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> dict[str, Any]:
    await _check_project(projects, project_id, workspace)
    rec = await data.get(project_id, table, record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec.to_dict()


@router.put("/{project_id}/tables/{table}/records/{record_id}")
async def update_record(
    project_id: str, table: str, record_id: str, body: RecordBody,
    data: DataStoreDep, projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> dict[str, Any]:
    await _check_project(projects, project_id, workspace)
    rec = await data.update(project_id, table, record_id, body.data)
    if rec is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec.to_dict()


@router.delete("/{project_id}/tables/{table}/records/{record_id}", status_code=204)
async def delete_record(
    project_id: str, table: str, record_id: str,
    data: DataStoreDep, projects: ProjectStoreDep, workspace: WorkspaceDep,
) -> None:
    await _check_project(projects, project_id, workspace)
    if not await data.delete(project_id, table, record_id):
        raise HTTPException(status_code=404, detail="Record not found")
