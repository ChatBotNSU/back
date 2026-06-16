from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from db.models import SecretRow
from services.secrets import Cipher


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _meta(row: SecretRow) -> dict[str, Any]:
    """Metadata only — never the decrypted value."""
    return {
        "id": row.id,
        "name": row.name,
        "workspace_id": row.workspace_id,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


class SQLSecretStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], cipher: Cipher) -> None:
        self._sf = session_factory
        self._cipher = cipher

    async def put(self, workspace_id: str, name: str, value: dict[str, Any]) -> str:
        encrypted = self._cipher.encrypt(json.dumps(value))
        async with self._sf() as session:
            async with session.begin():
                result = await session.execute(
                    select(SecretRow).where(
                        SecretRow.workspace_id == workspace_id, SecretRow.name == name
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    row.value_encrypted = encrypted
                    row.updated_at = _now()
                    return row.id
                secret_id = str(uuid.uuid4())
                session.add(SecretRow(
                    id=secret_id, workspace_id=workspace_id, name=name,
                    value_encrypted=encrypted, created_at=_now(), updated_at=_now(),
                ))
                return secret_id

    async def get_value(self, workspace_id: str, name: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            result = await session.execute(
                select(SecretRow).where(
                    SecretRow.workspace_id == workspace_id, SecretRow.name == name
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return json.loads(self._cipher.decrypt(row.value_encrypted))

    async def list_meta(self, workspace_id: str) -> list[dict[str, Any]]:
        async with self._sf() as session:
            result = await session.execute(
                select(SecretRow).where(SecretRow.workspace_id == workspace_id).order_by(SecretRow.name)
            )
            return [_meta(row) for row in result.scalars()]

    async def delete(self, workspace_id: str, name: str) -> bool:
        async with self._sf() as session:
            async with session.begin():
                result = await session.execute(
                    delete(SecretRow).where(
                        SecretRow.workspace_id == workspace_id, SecretRow.name == name
                    )
                )
                return result.rowcount > 0


class InMemorySecretStore:
    def __init__(self, cipher: Cipher | None = None) -> None:
        # (workspace_id, name) -> encrypted str (or plain JSON when no cipher)
        self._cipher = cipher
        self._data: dict[tuple[str, str], str] = {}
        self._meta: dict[tuple[str, str], dict[str, Any]] = {}

    def _enc(self, value: dict[str, Any]) -> str:
        raw = json.dumps(value)
        return self._cipher.encrypt(raw) if self._cipher else raw

    def _dec(self, blob: str) -> dict[str, Any]:
        raw = self._cipher.decrypt(blob) if self._cipher else blob
        return json.loads(raw)

    async def put(self, workspace_id: str, name: str, value: dict[str, Any]) -> str:
        key = (workspace_id, name)
        self._data[key] = self._enc(value)
        now = _now().isoformat()
        existing = self._meta.get(key)
        secret_id = existing["id"] if existing else str(uuid.uuid4())
        self._meta[key] = {
            "id": secret_id, "name": name, "workspace_id": workspace_id,
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        return secret_id

    async def get_value(self, workspace_id: str, name: str) -> dict[str, Any] | None:
        blob = self._data.get((workspace_id, name))
        return self._dec(blob) if blob is not None else None

    async def list_meta(self, workspace_id: str) -> list[dict[str, Any]]:
        return [m for (ws, _), m in self._meta.items() if ws == workspace_id]

    async def delete(self, workspace_id: str, name: str) -> bool:
        key = (workspace_id, name)
        existed = key in self._data
        self._data.pop(key, None)
        self._meta.pop(key, None)
        return existed
