"""Эндпойнты для пользовательских сабграфов с версионированием.

Сабграф не имеет своей таблицы в БД и идентифицируется парой
(owner_user_id, subgraph_name). Тело каждой версии лежит в S3 отдельным
файлом, метадата версий — в таблице `subgraph_versions` (db-service).

Эндпойнты симметричны с `/api/v1/chatbot/*`: история, latest, diff, save
с base_version_id/force и conflict detection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.middleware import get_current_active_user
from entities.User import User
from models.chatbot import Subgraph

from db.subgraph_request import (
    create_version,
    get_latest_version,
    get_version,
    list_versions,
    list_subgraph_names as db_list_subgraph_names,
    delete_subgraph as db_delete_subgraph,
)

from minio_controller.S3Client import S3Client
from utils.graph_logic import SubgraphAssistant, detect_subgraph_conflict


router = APIRouter()


# ───────────────── Schemas ─────────────────

class SaveSubgraphRequest(BaseModel):
    subgraph: Subgraph
    base_version_id: Optional[int] = None
    force: bool = False


class DiffResponse(BaseModel):
    added: list[str]
    deleted: list[str]
    modified: list[str]


# ───────────────── Helpers ─────────────────

def _make_s3_key(user_id: int, name: str) -> str:
    ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    return f"subgraphs/{user_id}/{name}/v_{ts}.json"


async def _save_new_version(
    s3: S3Client,
    sub: Subgraph,
    owner_user_id: int,
    author_id: int,
    parent_id: Optional[int],
) -> Subgraph:
    s3_key = _make_s3_key(owner_user_id, sub.name)
    s3.upload_subgraph_by_key(s3_key, sub)
    await create_version(
        owner_user_id=owner_user_id,
        subgraph_name=sub.name,
        author_id=author_id,
        s3_key=s3_key,
        parent_id=parent_id,
    )
    return sub


# ───────────────── Endpoints ─────────────────

@router.get("/subgraphs", response_model=List[str])
async def list_subgraphs(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Имена всех сабграфов текущего пользователя."""
    return await db_list_subgraph_names(current_user.id)


@router.post("/subgraphs", response_model=Subgraph, status_code=201)
async def create_subgraph(
    subgraph: Subgraph,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Создаёт первую версию сабграфа. 409 если сабграф с таким именем уже есть."""
    existing = await get_latest_version(current_user.id, subgraph.name)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Subgraph '{subgraph.name}' already exists",
        )
    return await _save_new_version(
        S3Client.get_instance(),
        subgraph,
        owner_user_id=current_user.id,
        author_id=current_user.id,
        parent_id=None,
    )


@router.get("/subgraph/{name}", response_model=Subgraph)
async def read_subgraph(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Тело самой свежей версии сабграфа."""
    latest = await get_latest_version(current_user.id, name)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Subgraph '{name}' not found")
    return S3Client.get_instance().download_subgraph_by_key(latest["s3_key"])


@router.put("/subgraph/{name}", response_model=Subgraph)
async def update_subgraph(
    name: str,
    body: SaveSubgraphRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Сохранение новой версии с логикой совместной работы (та же что у чатбота).

    - `force=True` → новая версия поверх latest без проверок.
    - `base_version_id == latest.id` → нет конфликта, новая версия.
    - Иначе тянем base/latest/incoming, `detect_subgraph_conflict`:
        * нет пересечений → автомерж через SubgraphAssistant.merge;
        * есть → 409 с обеими версиями.
    """
    if body.subgraph.name != name:
        raise HTTPException(
            status_code=400,
            detail=f"Path name '{name}' does not match body name '{body.subgraph.name}'",
        )

    s3 = S3Client.get_instance()
    incoming = body.subgraph
    latest_meta = await get_latest_version(current_user.id, name)

    if latest_meta is None:
        raise HTTPException(status_code=404, detail=f"Subgraph '{name}' not found")

    if body.force:
        return await _save_new_version(
            s3, incoming,
            owner_user_id=current_user.id,
            author_id=current_user.id,
            parent_id=latest_meta["id"],
        )

    if body.base_version_id == latest_meta["id"]:
        return await _save_new_version(
            s3, incoming,
            owner_user_id=current_user.id,
            author_id=current_user.id,
            parent_id=latest_meta["id"],
        )

    base_meta = await get_version(body.base_version_id) if body.base_version_id else None
    if base_meta is None:
        raise HTTPException(status_code=409, detail={
            "error": "base_version_not_found",
            "latest_version_id": latest_meta["id"],
        })

    base_obj   = s3.download_subgraph_by_key(base_meta["s3_key"])
    latest_obj = s3.download_subgraph_by_key(latest_meta["s3_key"])

    has_conflict, conflict_details = detect_subgraph_conflict(base_obj, latest_obj, incoming)

    if has_conflict:
        raise HTTPException(status_code=409, detail={
            "error": "merge_conflict",
            "latest_version_id": latest_meta["id"],
            "conflicting_nodes":    conflict_details["conflicting_nodes"],
            "conflicting_metadata": conflict_details["conflicting_metadata"],
            "your_version":  incoming.model_dump(),
            "their_version": latest_obj.model_dump(),
        })

    merged = SubgraphAssistant.merge(base_obj, latest_obj, incoming)
    return await _save_new_version(
        s3, merged,
        owner_user_id=current_user.id,
        author_id=current_user.id,
        parent_id=latest_meta["id"],
    )


@router.get("/subgraph/{name}/history")
async def get_subgraph_history(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return await list_versions(current_user.id, name)


@router.get("/subgraph/{name}/diff", response_model=DiffResponse)
async def get_subgraph_diff(
    name: str,
    v1: int,
    v2: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    s3 = S3Client.get_instance()
    v1_meta = await get_version(v1)
    v2_meta = await get_version(v2)
    if not v1_meta or not v2_meta:
        raise HTTPException(status_code=404, detail="One or both versions not found")
    # Защита от чужих версий: оба обязаны принадлежать пользователю и этому имени.
    for meta in (v1_meta, v2_meta):
        if meta.get("owner_user_id") != current_user.id or meta.get("subgraph_name") != name:
            raise HTTPException(status_code=404, detail="Version does not belong to this subgraph")

    return DiffResponse(**SubgraphAssistant.compare(
        s3.download_subgraph_by_key(v1_meta["s3_key"]),
        s3.download_subgraph_by_key(v2_meta["s3_key"]),
    ))


@router.delete("/subgraph/{name}")
async def delete_subgraph(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Удаляет все версии сабграфа из БД. S3-объекты при этом остаются — их
    можно подчистить отдельным garbage-collector-ом. 404 если ничего не было."""
    if await get_latest_version(current_user.id, name) is None:
        raise HTTPException(status_code=404, detail=f"Subgraph '{name}' not found")
    result = await db_delete_subgraph(current_user.id, name)
    return {"ok": True, "name": name, **result}
