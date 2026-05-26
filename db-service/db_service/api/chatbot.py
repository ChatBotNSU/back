from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.session import get_session
from db.orm_models import VersionStatusEnum
from db.crud.chatbot import (
    create_chatbot,
    list_chatbots_by_user,
    delete_chatbot,
    create_version,
    get_version,
    get_latest_version,
    list_versions,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class VersionOut(BaseModel):
    id: int
    chatbot_id: int
    parent_id: Optional[int]
    s3_key: str
    status: str
    author_id: int
    created_at: str

    @classmethod
    def from_orm(cls, v):
        return cls(
            id=v.id,
            chatbot_id=v.chatbot_id,
            parent_id=v.parent_id,
            s3_key=v.s3_key,
            status=v.status.value,
            author_id=v.author_id,
            created_at=v.created_at.isoformat(),
        )


class CreateVersionRequest(BaseModel):
    chatbot_id: int
    author_id: int
    s3_key: str
    parent_id: Optional[int] = None
    status: str = "DRAFT"


@router.post("/create")
async def create_chatbot_endpoint(
    name: str,
    description: str,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    bot = await create_chatbot(session, name=name, description=description, user_id=user_id)
    return {"id": bot.id, "name": bot.name}


@router.get("/list")
async def list_chatbots_endpoint(
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    bots = await list_chatbots_by_user(session, user_id)
    return [{"id": b.id, "name": b.name, "description": b.description} for b in bots]


@router.delete("/delete")
async def delete_chatbot_endpoint(
    bot_id: int,
    session: AsyncSession = Depends(get_session),
):
    ok = await delete_chatbot(session, bot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chatbot not found")
    return {"ok": True}


@router.post("/version", response_model=VersionOut)
async def create_version_endpoint(
    body: CreateVersionRequest,
    session: AsyncSession = Depends(get_session),
):
    """Создаёт новую запись версии в БД. Вызывается из administration-backend после загрузки в S3."""
    status_enum = VersionStatusEnum(body.status)
    version = await create_version(
        session,
        chatbot_id=body.chatbot_id,
        author_id=body.author_id,
        s3_key=body.s3_key,
        parent_id=body.parent_id,
        status=status_enum,
    )
    return VersionOut.from_orm(version)


@router.get("/{bot_id}/versions", response_model=list[VersionOut])
async def list_versions_endpoint(
    bot_id: int,
    session: AsyncSession = Depends(get_session),
):
    """История всех версий бота от новой к старой."""
    versions = await list_versions(session, bot_id)
    return [VersionOut.from_orm(v) for v in versions]


@router.get("/{bot_id}/versions/latest", response_model=VersionOut)
async def get_latest_version_endpoint(
    bot_id: int,
    session: AsyncSession = Depends(get_session),
):
    version = await get_latest_version(session, bot_id)
    if not version:
        raise HTTPException(status_code=404, detail="No versions found for this bot")
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
