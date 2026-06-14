"""
Project-scoped built-in data tables (schemaless rows), used by the `database`
node. A "table" is just a string namespace within a project; rows are JSON.

Filtering by `where` is done in Python so it works identically on SQLite and
Postgres (fine for moderate tables; push down to JSONB for very large ones).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import delete, distinct, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from db.models import DataRecordRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DataRecord:
    id: str
    project_id: str
    table: str
    data: dict[str, Any]
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "table": self.table, "data": self.data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


def _matches(data: dict[str, Any], where: dict[str, Any]) -> bool:
    return all(data.get(k) == v for k, v in where.items())


@runtime_checkable
class DataStore(Protocol):
    async def insert(self, project_id: str, table: str, data: dict[str, Any]) -> DataRecord: ...
    async def get(self, project_id: str, table: str, record_id: str) -> DataRecord | None: ...
    async def query(self, project_id: str, table: str, where: dict[str, Any], limit: int = 100) -> list[DataRecord]: ...
    async def update(self, project_id: str, table: str, record_id: str, data: dict[str, Any]) -> DataRecord | None: ...
    async def delete(self, project_id: str, table: str, record_id: str) -> bool: ...
    async def list_tables(self, project_id: str) -> list[str]: ...


def _row_to_record(row: DataRecordRow) -> DataRecord:
    return DataRecord(
        id=row.id, project_id=row.project_id, table=row.table_name, data=row.data or {},
        created_at=row.created_at, updated_at=row.updated_at,
    )


class SQLDataStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def insert(self, project_id: str, table: str, data: dict[str, Any]) -> DataRecord:
        rec = DataRecord(id=str(uuid.uuid4()), project_id=project_id, table=table, data=data)
        async with self._sf() as session:
            async with session.begin():
                session.add(DataRecordRow(
                    id=rec.id, project_id=project_id, table_name=table, data=data,
                    created_at=rec.created_at, updated_at=rec.updated_at,
                ))
        return rec

    async def get(self, project_id: str, table: str, record_id: str) -> DataRecord | None:
        async with self._sf() as session:
            row = await session.get(DataRecordRow, record_id)
            if row is None or row.project_id != project_id or row.table_name != table:
                return None
            return _row_to_record(row)

    async def query(self, project_id, table, where, limit=100) -> list[DataRecord]:
        async with self._sf() as session:
            result = await session.execute(
                select(DataRecordRow).where(
                    DataRecordRow.project_id == project_id,
                    DataRecordRow.table_name == table,
                ).order_by(DataRecordRow.created_at)
            )
            out: list[DataRecord] = []
            for row in result.scalars():
                rec = _row_to_record(row)
                if _matches(rec.data, where or {}):
                    out.append(rec)
                if len(out) >= limit:
                    break
            return out

    async def update(self, project_id, table, record_id, data) -> DataRecord | None:
        async with self._sf() as session:
            async with session.begin():
                row = await session.get(DataRecordRow, record_id)
                if row is None or row.project_id != project_id or row.table_name != table:
                    return None
                row.data = {**(row.data or {}), **data}
                row.updated_at = _now()
                return _row_to_record(row)

    async def delete(self, project_id, table, record_id) -> bool:
        async with self._sf() as session:
            async with session.begin():
                row = await session.get(DataRecordRow, record_id)
                if row is None or row.project_id != project_id or row.table_name != table:
                    return False
                await session.execute(delete(DataRecordRow).where(DataRecordRow.id == record_id))
                return True

    async def list_tables(self, project_id: str) -> list[str]:
        async with self._sf() as session:
            result = await session.execute(
                select(distinct(DataRecordRow.table_name)).where(
                    DataRecordRow.project_id == project_id
                )
            )
            return sorted(r for (r,) in result.all())


class InMemoryDataStore:
    def __init__(self) -> None:
        self._rows: dict[str, DataRecord] = {}

    async def insert(self, project_id, table, data) -> DataRecord:
        rec = DataRecord(id=str(uuid.uuid4()), project_id=project_id, table=table, data=dict(data))
        self._rows[rec.id] = rec
        return rec

    def _own(self, rec: DataRecord | None, project_id, table) -> DataRecord | None:
        if rec and rec.project_id == project_id and rec.table == table:
            return rec
        return None

    async def get(self, project_id, table, record_id) -> DataRecord | None:
        return self._own(self._rows.get(record_id), project_id, table)

    async def query(self, project_id, table, where, limit=100) -> list[DataRecord]:
        out = [
            r for r in self._rows.values()
            if r.project_id == project_id and r.table == table and _matches(r.data, where or {})
        ]
        out.sort(key=lambda r: r.created_at)
        return out[:limit]

    async def update(self, project_id, table, record_id, data) -> DataRecord | None:
        rec = self._own(self._rows.get(record_id), project_id, table)
        if rec is None:
            return None
        rec.data = {**rec.data, **data}
        rec.updated_at = _now()
        return rec

    async def delete(self, project_id, table, record_id) -> bool:
        rec = self._own(self._rows.get(record_id), project_id, table)
        if rec is None:
            return False
        self._rows.pop(record_id, None)
        return True

    async def list_tables(self, project_id: str) -> list[str]:
        return sorted({r.table for r in self._rows.values() if r.project_id == project_id})


# ─── Module-level active store (reached by the `database` node handler) ─────────

_active: DataStore | None = None


def set_active_store(store: DataStore | None) -> None:
    global _active
    _active = store


def active() -> DataStore | None:
    return _active
