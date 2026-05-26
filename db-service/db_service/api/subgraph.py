from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from db.orm_models import VersionStatusEnum
from db.crud.subgraph import (
    create_version,
    get_version,
    get_latest_version,
    list_versions,
    list_subgraph_names,
    delete_subgraph,
)

router = APIRouter()


class VersionOut(BaseModel):
    id: int
    owner_user_id: int
    subgraph_name: str
    parent_id: Optional[int]
    s3_key: str
    status: str
    author_id: int
    created_at: str

    @classmethod
    def from_orm(cls, v):
        return cls(
            id=v.id,
            owner_user_id=v.owner_user_id,
            subgraph_name=v.subgraph_name,
            parent_id=v.parent_id,
            s3_key=v.s3_key,
            status=v.status.value,
            author_id=v.author_id,
            created_at=v.created_at.isoformat(),
        )


class CreateVersionRequest(BaseModel):
    owner_user_id: int
    subgraph_name: str
    author_id: int
    s3_key: str
    parent_id: Optional[int] = None
    status: str = "DRAFT"


@router.post("/version", response_model=VersionOut)
async def create_version_endpoint(
    body: CreateVersionRequest,
    session: AsyncSession = Depends(get_session),
):
    status_enum = VersionStatusEnum(body.status)
    version = await create_version(
        session,
        owner_user_id=body.owner_user_id,
        subgraph_name=body.subgraph_name,
        author_id=body.author_id,
        s3_key=body.s3_key,
        parent_id=body.parent_id,
        status=status_enum,
    )
    return VersionOut.from_orm(version)


@router.get("/version/{version_id}", response_model=VersionOut)
async def get_version_endpoint(
    version_id: int,
    session: AsyncSession = Depends(get_session),
):
    version = await get_version(session, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return VersionOut.from_orm(version)


@router.get("/{owner_user_id}/list", response_model=list[str])
async def list_subgraphs_endpoint(
    owner_user_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Уникальные имена всех сабграфов пользователя."""
    return await list_subgraph_names(session, owner_user_id)


@router.get("/{owner_user_id}/{subgraph_name}/versions", response_model=list[VersionOut])
async def list_versions_endpoint(
    owner_user_id: int,
    subgraph_name: str,
    session: AsyncSession = Depends(get_session),
):
    versions = await list_versions(session, owner_user_id, subgraph_name)
    return [VersionOut.from_orm(v) for v in versions]


@router.get("/{owner_user_id}/{subgraph_name}/versions/latest", response_model=VersionOut)
async def get_latest_version_endpoint(
    owner_user_id: int,
    subgraph_name: str,
    session: AsyncSession = Depends(get_session),
):
    version = await get_latest_version(session, owner_user_id, subgraph_name)
    if not version:
        raise HTTPException(status_code=404, detail="No versions found for this subgraph")
    return VersionOut.from_orm(version)


@router.delete("/{owner_user_id}/{subgraph_name}")
async def delete_subgraph_endpoint(
    owner_user_id: int,
    subgraph_name: str,
    session: AsyncSession = Depends(get_session),
):
    deleted = await delete_subgraph(session, owner_user_id, subgraph_name)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Subgraph not found")
    return {"ok": True, "deleted_versions": deleted}
