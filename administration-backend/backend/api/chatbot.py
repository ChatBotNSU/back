from typing import Annotated, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fastapi import Depends, APIRouter
from api.middleware import get_current_active_user
from entities.User import User
from models.chatbot import Chatbot, ChatbotUnassigned

from db.chatbot_request import (
    get_chatbots,
    create_chatbot,
    delete_chatbot,
    create_version,
    get_latest_version,
    get_version,
    list_versions,
)

from minio_controller.S3Client import S3Client
from utils.graph_logic import GraphAssistant, detect_conflict

router = APIRouter()


# ───────────────── Schemas ─────────────────

class SaveChatbotRequest(BaseModel):
    chatbot: ChatbotUnassigned
    # ID версии с которой юзер начал редактирование
    base_version_id: Optional[int] = None
    # force=True: юзер явно выбрал свою версию после конфликта — сохраняем без проверок
    force: bool = False


class DiffResponse(BaseModel):
    added: list[str]
    deleted: list[str]
    modified: list[str]


# ───────────────── Helpers ─────────────────

def _make_s3_key(chatbot_id: int) -> str:
    ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    return f"bots/{chatbot_id}/v_{ts}.json"


async def _save_new_version(
    s3: S3Client,
    chatbot_obj: Chatbot,
    chatbot_id: int,
    author_id: int,
    parent_id: Optional[int],
) -> Chatbot:
    s3_key = _make_s3_key(chatbot_id)
    s3.upload_chatbot_by_key(s3_key, chatbot_obj)
    await create_version(
        chatbot_id=chatbot_id,
        author_id=author_id,
        s3_key=s3_key,
        parent_id=parent_id,
    )
    return chatbot_obj


# ───────────────── Endpoints ─────────────────

@router.get("/chatbots")
async def read_chatbots(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return await get_chatbots(current_user.id)


@router.post("/chatbots", response_model=Chatbot)
async def create_chatbot_endpoint(
    chatbot: ChatbotUnassigned,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    result = await create_chatbot(
        current_user.id,
        chatbot.bot_name,
        "Chatbots dont have descriptions and dont cry",
    )
    bot_id = result["id"]
    chatbot_obj = Chatbot(**chatbot.model_dump(), bot_id=bot_id)
    return await _save_new_version(S3Client.get_instance(), chatbot_obj, bot_id, current_user.id, parent_id=None)


@router.get("/chatbot/{chatbot_id}", response_model=Chatbot)
async def read_chatbot(
    chatbot_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # TODO: check ownership
    latest = await get_latest_version(chatbot_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No versions found")
    return S3Client.get_instance().download_chatbot_by_key(latest["s3_key"])


@router.post("/chatbot/{chatbot_id}", response_model=Chatbot)
async def update_chatbot(
    chatbot_id: int,
    body: SaveChatbotRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    Сохранение с логикой совместной работы.

    Сценарий А — нет конфликта:
        base_version_id == latest → просто сохраняем новую версию.

    Сценарий Б — конфликт, разные узлы:
        Автомерж на сервере, юзер получает результат незаметно.

    Сценарий В — конфликт, один и тот же узел:
        HTTP 409. В теле ответа — обе полные версии (твоя и чужая).
        Юзер выбирает одну и переотправляет с force=True.

    Сценарий Г — force=True:
        Юзер явно выбрал свою версию после просмотра конфликта.
        Сохраняем поверх latest без проверок.
    """
    # TODO: check ownership
    s3 = S3Client.get_instance()
    incoming_obj = Chatbot(**body.chatbot.model_dump(), bot_id=chatbot_id)
    latest_meta = await get_latest_version(chatbot_id)

    # ── Первое сохранение ────────────────────────────────────────────────
    if latest_meta is None:
        return await _save_new_version(s3, incoming_obj, chatbot_id, current_user.id, parent_id=None)

    # ── Г. Юзер явно выбрал версию после конфликта ──────────────────────
    if body.force:
        return await _save_new_version(s3, incoming_obj, chatbot_id, current_user.id, parent_id=latest_meta["id"])

    # ── А. Нет конфликта ─────────────────────────────────────────────────
    if body.base_version_id == latest_meta["id"]:
        return await _save_new_version(s3, incoming_obj, chatbot_id, current_user.id, parent_id=latest_meta["id"])

    # ── Кто-то сохранил пока юзер редактировал ──────────────────────────
    base_meta = await get_version(body.base_version_id) if body.base_version_id else None
    if base_meta is None:
        raise HTTPException(status_code=409, detail={
            "error": "base_version_not_found",
            "latest_version_id": latest_meta["id"],
        })

    base_obj   = s3.download_chatbot_by_key(base_meta["s3_key"])
    latest_obj = s3.download_chatbot_by_key(latest_meta["s3_key"])

    has_conflict, conflict_details = detect_conflict(base_obj, latest_obj, incoming_obj)

    # ── В. Конфликт — отдаём обе версии юзеру на выбор ──────────────────
    if has_conflict:
        raise HTTPException(status_code=409, detail={
            "error": "merge_conflict",
            "latest_version_id": latest_meta["id"],
            "conflicting_nodes": conflict_details["conflicting_nodes"],
            # Две полные версии — фронт показывает их рядом, юзер выбирает
            "your_version":  incoming_obj.model_dump(),
            "their_version": latest_obj.model_dump(),
        })

    # ── Б. Автомерж — изменения в разных узлах ──────────────────────────
    merged_obj = GraphAssistant.merge(base_obj, latest_obj, incoming_obj)
    return await _save_new_version(s3, merged_obj, chatbot_id, current_user.id, parent_id=latest_meta["id"])


@router.get("/chatbot/{chatbot_id}/history")
async def get_chatbot_history(
    chatbot_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # TODO: check ownership
    return await list_versions(chatbot_id)


@router.get("/chatbot/{chatbot_id}/diff", response_model=DiffResponse)
async def get_chatbot_diff(
    chatbot_id: int,
    v1: int,
    v2: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """GET /chatbot/{id}/diff?v1=3&v2=7"""
    # TODO: check ownership
    s3 = S3Client.get_instance()

    v1_meta = await get_version(v1)
    v2_meta = await get_version(v2)
    if not v1_meta or not v2_meta:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    return DiffResponse(**GraphAssistant.compare(
        s3.download_chatbot_by_key(v1_meta["s3_key"]),
        s3.download_chatbot_by_key(v2_meta["s3_key"]),
    ))


@router.delete("/chatbot/{chatbot_id}")
async def delete_chatbot_endpoint(
    chatbot_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # TODO: Check ownership
    await delete_chatbot(chatbot_id)
