from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from db.models import BotRow


# ─── Domain object ────────────────────────────────────────────────────────────

@dataclass
class BotConfig:
    id: str
    name: str
    flow_id: str
    channel: str
    token: str = ""
    webhook_secret: str = ""
    workspace_id: str = "default"
    project_id: str = ""
    metadata: dict = field(default_factory=dict)


# ─── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class BotStore(Protocol):
    async def get_by_id(self, bot_id: str, workspace_id: str | None = None) -> BotConfig | None: ...
    async def get_by_token(self, token: str) -> BotConfig | None: ...
    async def save(self, bot: BotConfig) -> None: ...
    async def delete(self, bot_id: str, workspace_id: str | None = None) -> None: ...
    async def list_all(
        self, workspace_id: str | None = None, project_id: str | None = None
    ) -> list[BotConfig]: ...


# ─── Serialisation helpers ────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_bot(row: BotRow) -> BotConfig:
    return BotConfig(
        id=row.id,
        name=row.name,
        flow_id=row.flow_id,
        channel=row.channel,
        token=row.token,
        webhook_secret=row.webhook_secret,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        metadata=row.meta or {},
    )


def _bot_to_row(bot: BotConfig) -> BotRow:
    now = _now()
    return BotRow(
        id=bot.id,
        workspace_id=bot.workspace_id,
        project_id=bot.project_id,
        name=bot.name,
        flow_id=bot.flow_id,
        channel=bot.channel,
        token=bot.token,
        webhook_secret=bot.webhook_secret,
        meta=bot.metadata,
        created_at=now,
        updated_at=now,
    )


# ─── SQL implementation ───────────────────────────────────────────────────────

class SQLBotStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_by_id(self, bot_id: str, workspace_id: str | None = None) -> BotConfig | None:
        async with self._sf() as session:
            row = await session.get(BotRow, bot_id)
            if row is None:
                return None
            if workspace_id is not None and row.workspace_id != workspace_id:
                return None
            return _row_to_bot(row)

    async def get_by_token(self, token: str) -> BotConfig | None:
        async with self._sf() as session:
            result = await session.execute(
                select(BotRow).where(BotRow.token == token).limit(1)
            )
            row = result.scalar_one_or_none()
            return _row_to_bot(row) if row else None

    async def save(self, bot: BotConfig) -> None:
        async with self._sf() as session:
            async with session.begin():
                existing = await session.get(BotRow, bot.id)
                if existing:
                    existing.workspace_id = bot.workspace_id
                    existing.project_id = bot.project_id
                    existing.name = bot.name
                    existing.flow_id = bot.flow_id
                    existing.channel = bot.channel
                    existing.token = bot.token
                    existing.webhook_secret = bot.webhook_secret
                    existing.meta = bot.metadata
                    existing.updated_at = _now()
                else:
                    session.add(_bot_to_row(bot))

    async def delete(self, bot_id: str, workspace_id: str | None = None) -> None:
        async with self._sf() as session:
            async with session.begin():
                if workspace_id is not None:
                    row = await session.get(BotRow, bot_id)
                    if row is None or row.workspace_id != workspace_id:
                        return
                await session.execute(delete(BotRow).where(BotRow.id == bot_id))

    async def list_all(
        self, workspace_id: str | None = None, project_id: str | None = None
    ) -> list[BotConfig]:
        async with self._sf() as session:
            stmt = select(BotRow)
            if workspace_id is not None:
                stmt = stmt.where(BotRow.workspace_id == workspace_id)
            if project_id is not None:
                stmt = stmt.where(BotRow.project_id == project_id)
            result = await session.execute(stmt.order_by(BotRow.name))
            return [_row_to_bot(row) for row in result.scalars()]


# ─── In-memory fallback ───────────────────────────────────────────────────────

class InMemoryBotStore:
    def __init__(self) -> None:
        self._by_id: dict[str, BotConfig] = {}
        self._by_token: dict[str, BotConfig] = {}

    async def get_by_id(self, bot_id: str, workspace_id: str | None = None) -> BotConfig | None:
        bot = self._by_id.get(bot_id)
        if bot is None:
            return None
        if workspace_id is not None and bot.workspace_id != workspace_id:
            return None
        return bot

    async def get_by_token(self, token: str) -> BotConfig | None:
        return self._by_token.get(token)

    async def save(self, bot: BotConfig) -> None:
        self._by_id[bot.id] = bot
        if bot.token:
            self._by_token[bot.token] = bot

    async def delete(self, bot_id: str, workspace_id: str | None = None) -> None:
        bot = self._by_id.get(bot_id)
        if bot is None:
            return
        if workspace_id is not None and bot.workspace_id != workspace_id:
            return
        self._by_id.pop(bot_id, None)
        if bot.token:
            self._by_token.pop(bot.token, None)

    async def list_all(
        self, workspace_id: str | None = None, project_id: str | None = None
    ) -> list[BotConfig]:
        return [
            b for b in self._by_id.values()
            if (workspace_id is None or b.workspace_id == workspace_id)
            and (project_id is None or b.project_id == project_id)
        ]
