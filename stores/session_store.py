from __future__ import annotations

from typing import Protocol, runtime_checkable

from models.session import Session

# ─── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class SessionStore(Protocol):
    async def get(self, session_id: str) -> Session | None: ...
    async def get_by_key(self, session_key: str) -> Session | None: ...
    async def save(self, session: Session) -> None: ...
    async def delete(self, session_id: str) -> None: ...
    async def list_by_flow(self, flow_id: str, limit: int = 50) -> list[Session]: ...


# ─── Redis implementation ──────────────────────────────────────────────────────

class RedisSessionStore:
    """
    Session data: SETEX session:{id} → JSON blob
    Session key index: SETEX session_key:{key} → session_id
    Flow index: ZADD flow_sessions:{flow_id} score=timestamp member=session_id
    """

    def __init__(self, redis: object, ttl: int = 604_800) -> None:
        self._r = redis  # redis.asyncio.Redis
        self._ttl = ttl

    async def get(self, session_id: str) -> Session | None:
        data = await self._r.get(f"session:{session_id}")
        if data is None:
            return None
        return Session.model_validate_json(data)

    async def get_by_key(self, session_key: str) -> Session | None:
        session_id = await self._r.get(f"session_key:{session_key}")
        if session_id is None:
            return None
        sid = session_id.decode() if isinstance(session_id, bytes) else session_id
        return await self.get(sid)

    async def save(self, session: Session) -> None:
        session.touch()
        payload = session.model_dump_json()
        await self._r.set(f"session:{session.id}", payload, ex=self._ttl)

        # Flow index (sorted set, score = unix timestamp for ordering)
        score = session.updated_at.timestamp()
        await self._r.zadd(f"flow_sessions:{session.flow_id}", {session.id: score})
        await self._r.expire(f"flow_sessions:{session.flow_id}", self._ttl)

        # Session key index (for channel:user_id lookup)
        if key := session.variables.get("__session_key__"):
            await self._r.set(f"session_key:{key}", session.id, ex=self._ttl)

    async def delete(self, session_id: str) -> None:
        session = await self.get(session_id)
        if session:
            if key := session.variables.get("__session_key__"):
                await self._r.delete(f"session_key:{key}")
            await self._r.zrem(f"flow_sessions:{session.flow_id}", session_id)
        await self._r.delete(f"session:{session_id}")

    async def list_by_flow(self, flow_id: str, limit: int = 50) -> list[Session]:
        # Descending by updated_at score
        raw_ids = await self._r.zrevrange(f"flow_sessions:{flow_id}", 0, limit - 1)
        sessions: list[Session] = []
        for raw in raw_ids:
            sid = raw.decode() if isinstance(raw, bytes) else raw
            s = await self.get(sid)
            if s is not None:
                sessions.append(s)
        return sessions


# ─── In-memory fallback (dev / unit tests without Redis) ──────────────────────

class InMemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, Session] = {}
        self._key_index: dict[str, str] = {}

    async def get(self, session_id: str) -> Session | None:
        return self._data.get(session_id)

    async def get_by_key(self, session_key: str) -> Session | None:
        sid = self._key_index.get(session_key)
        return self._data.get(sid) if sid else None

    async def save(self, session: Session) -> None:
        session.touch()
        self._data[session.id] = session
        if key := session.variables.get("__session_key__"):
            self._key_index[key] = session.id

    async def delete(self, session_id: str) -> None:
        session = self._data.pop(session_id, None)
        if session:
            if key := session.variables.get("__session_key__"):
                self._key_index.pop(key, None)

    async def list_by_flow(self, flow_id: str, limit: int = 50) -> list[Session]:
        result = [s for s in self._data.values() if s.flow_id == flow_id]
        result.sort(key=lambda s: s.updated_at, reverse=True)
        return result[:limit]
