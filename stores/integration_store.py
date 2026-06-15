"""
Named, project-scoped integrations (kind = provider | http | db).

config shape by kind:
  provider → {"provider": "bitrix24", "secret_ref": "bx-creds", ...extra}
  http     → {"base_url": "...", "headers": {...}, "secret_ref": "..."}
  db       → {"driver": "postgresql+asyncpg", "secret_ref": "pg-dsn"} or {"dsn": "..."}

Credentials never live here directly — they reference a secret by name.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from db.models import IntegrationRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Integration:
    id: str
    project_id: str
    name: str
    kind: str
    config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "project_id": self.project_id, "name": self.name,
            "kind": self.kind, "config": self.config,
            "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat(),
        }


@runtime_checkable
class IntegrationStore(Protocol):
    async def put(self, project_id: str, name: str, kind: str, config: dict[str, Any]) -> Integration: ...
    async def get_by_name(self, project_id: str, name: str) -> Integration | None: ...
    async def list_all(self, project_id: str) -> list[Integration]: ...
    async def delete(self, project_id: str, name: str) -> bool: ...


def _row(r: IntegrationRow) -> Integration:
    return Integration(id=r.id, project_id=r.project_id, name=r.name, kind=r.kind,
                       config=r.config or {}, created_at=r.created_at, updated_at=r.updated_at)


class SQLIntegrationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def put(self, project_id, name, kind, config) -> Integration:
        async with self._sf() as session:
            async with session.begin():
                result = await session.execute(
                    select(IntegrationRow).where(
                        IntegrationRow.project_id == project_id, IntegrationRow.name == name)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.kind = kind
                    row.config = config
                    row.updated_at = _now()
                    return _row(row)
                integ = IntegrationRow(
                    id=str(uuid.uuid4()), project_id=project_id, name=name, kind=kind,
                    config=config, created_at=_now(), updated_at=_now(),
                )
                session.add(integ)
                return _row(integ)

    async def get_by_name(self, project_id, name) -> Integration | None:
        async with self._sf() as session:
            result = await session.execute(
                select(IntegrationRow).where(
                    IntegrationRow.project_id == project_id, IntegrationRow.name == name)
            )
            row = result.scalar_one_or_none()
            return _row(row) if row else None

    async def list_all(self, project_id) -> list[Integration]:
        async with self._sf() as session:
            result = await session.execute(
                select(IntegrationRow).where(IntegrationRow.project_id == project_id).order_by(IntegrationRow.name)
            )
            return [_row(r) for r in result.scalars()]

    async def delete(self, project_id, name) -> bool:
        async with self._sf() as session:
            async with session.begin():
                result = await session.execute(
                    delete(IntegrationRow).where(
                        IntegrationRow.project_id == project_id, IntegrationRow.name == name)
                )
                return result.rowcount > 0


class InMemoryIntegrationStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], Integration] = {}

    async def put(self, project_id, name, kind, config) -> Integration:
        key = (project_id, name)
        existing = self._data.get(key)
        integ = Integration(
            id=existing.id if existing else str(uuid.uuid4()),
            project_id=project_id, name=name, kind=kind, config=config,
            created_at=existing.created_at if existing else _now(), updated_at=_now(),
        )
        self._data[key] = integ
        return integ

    async def get_by_name(self, project_id, name) -> Integration | None:
        return self._data.get((project_id, name))

    async def list_all(self, project_id) -> list[Integration]:
        return [i for (p, _), i in self._data.items() if p == project_id]

    async def delete(self, project_id, name) -> bool:
        return self._data.pop((project_id, name), None) is not None


# ─── Module-level active store + resolver (node handlers reach in here) ─────────

_active: IntegrationStore | None = None


def set_active_store(store: IntegrationStore | None) -> None:
    global _active
    _active = store


async def resolve(project_id: str, name: str) -> Integration | None:
    if not name or _active is None or not project_id:
        return None
    return await _active.get_by_name(project_id, name)
