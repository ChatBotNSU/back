from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from db.models import UserRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    workspace_id: str
    name: str = ""
    created_at: datetime = field(default_factory=_now)


@runtime_checkable
class UserStore(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: str) -> User | None: ...
    async def create(self, user: User) -> None: ...


def _row_to_user(row: UserRow) -> User:
    return User(
        id=row.id, email=row.email, password_hash=row.password_hash,
        workspace_id=row.workspace_id, name=row.name, created_at=row.created_at,
    )


class SQLUserStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_by_email(self, email: str) -> User | None:
        async with self._sf() as session:
            result = await session.execute(select(UserRow).where(UserRow.email == email.lower()))
            row = result.scalar_one_or_none()
            return _row_to_user(row) if row else None

    async def get_by_id(self, user_id: str) -> User | None:
        async with self._sf() as session:
            row = await session.get(UserRow, user_id)
            return _row_to_user(row) if row else None

    async def create(self, user: User) -> None:
        async with self._sf() as session:
            async with session.begin():
                session.add(UserRow(
                    id=user.id, email=user.email.lower(), password_hash=user.password_hash,
                    workspace_id=user.workspace_id, name=user.name, created_at=user.created_at,
                ))


class InMemoryUserStore:
    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}
        self._by_email: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email.lower())

    async def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    async def create(self, user: User) -> None:
        self._by_id[user.id] = user
        self._by_email[user.email.lower()] = user


def new_user(email: str, password_hash: str, name: str = "") -> User:
    return User(
        id=str(uuid.uuid4()),
        email=email.lower(),
        password_hash=password_hash,
        workspace_id=str(uuid.uuid4()),  # each user gets an isolated workspace
        name=name,
    )
