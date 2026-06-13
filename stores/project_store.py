from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from db.models import ProjectRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Project:
    id: str
    workspace_id: str
    name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@runtime_checkable
class ProjectStore(Protocol):
    async def get(self, project_id: str, workspace_id: str | None = None) -> Project | None: ...
    async def save(self, project: Project) -> None: ...
    async def delete(self, project_id: str, workspace_id: str | None = None) -> None: ...
    async def list_all(self, workspace_id: str | None = None) -> list[Project]: ...


def _row_to_project(row: ProjectRow) -> Project:
    return Project(
        id=row.id, workspace_id=row.workspace_id, name=row.name,
        description=row.description, metadata=row.meta or {},
        created_at=row.created_at, updated_at=row.updated_at,
    )


class SQLProjectStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get(self, project_id: str, workspace_id: str | None = None) -> Project | None:
        async with self._sf() as session:
            row = await session.get(ProjectRow, project_id)
            if row is None or (workspace_id is not None and row.workspace_id != workspace_id):
                return None
            return _row_to_project(row)

    async def save(self, project: Project) -> None:
        async with self._sf() as session:
            async with session.begin():
                existing = await session.get(ProjectRow, project.id)
                if existing:
                    existing.name = project.name
                    existing.description = project.description
                    existing.meta = project.metadata
                    existing.updated_at = _now()
                else:
                    session.add(ProjectRow(
                        id=project.id, workspace_id=project.workspace_id,
                        name=project.name, description=project.description,
                        meta=project.metadata, created_at=_now(), updated_at=_now(),
                    ))

    async def delete(self, project_id: str, workspace_id: str | None = None) -> None:
        async with self._sf() as session:
            async with session.begin():
                if workspace_id is not None:
                    row = await session.get(ProjectRow, project_id)
                    if row is None or row.workspace_id != workspace_id:
                        return
                await session.execute(delete(ProjectRow).where(ProjectRow.id == project_id))

    async def list_all(self, workspace_id: str | None = None) -> list[Project]:
        async with self._sf() as session:
            stmt = select(ProjectRow)
            if workspace_id is not None:
                stmt = stmt.where(ProjectRow.workspace_id == workspace_id)
            result = await session.execute(stmt.order_by(ProjectRow.name))
            return [_row_to_project(row) for row in result.scalars()]


class InMemoryProjectStore:
    def __init__(self) -> None:
        self._data: dict[str, Project] = {}

    async def get(self, project_id: str, workspace_id: str | None = None) -> Project | None:
        p = self._data.get(project_id)
        if p is None or (workspace_id is not None and p.workspace_id != workspace_id):
            return None
        return p

    async def save(self, project: Project) -> None:
        project.updated_at = _now()
        self._data[project.id] = project

    async def delete(self, project_id: str, workspace_id: str | None = None) -> None:
        p = self._data.get(project_id)
        if p is None or (workspace_id is not None and p.workspace_id != workspace_id):
            return
        self._data.pop(project_id, None)

    async def list_all(self, workspace_id: str | None = None) -> list[Project]:
        return [
            p for p in self._data.values()
            if workspace_id is None or p.workspace_id == workspace_id
        ]


def new_project(workspace_id: str, name: str, description: str = "") -> Project:
    return Project(id=str(uuid.uuid4()), workspace_id=workspace_id, name=name, description=description)
