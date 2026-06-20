from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeadLetterEntry:
    flow_id: str
    error: str
    kind: str = "exception"  # "exception" (raised) | "flow_error" (ERROR state)
    session_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeadLetterEntry":
        return cls(**data)


@runtime_checkable
class DeadLetterStore(Protocol):
    async def push(self, entry: DeadLetterEntry) -> None: ...
    async def list(self, limit: int = 100) -> list[DeadLetterEntry]: ...
    async def count(self) -> int: ...
    async def clear(self) -> None: ...


class RedisDeadLetterStore:
    """Newest-first capped list in Redis (LPUSH + LTRIM)."""

    def __init__(self, redis: object, key: str = "dead_letter", max_len: int = 1000) -> None:
        self._r = redis
        self._key = key
        self._max = max_len

    async def push(self, entry: DeadLetterEntry) -> None:
        await self._r.lpush(self._key, json.dumps(entry.to_dict()))
        await self._r.ltrim(self._key, 0, self._max - 1)

    async def list(self, limit: int = 100) -> list[DeadLetterEntry]:
        raw = await self._r.lrange(self._key, 0, limit - 1)
        out: list[DeadLetterEntry] = []
        for item in raw:
            text = item.decode() if isinstance(item, bytes) else item
            out.append(DeadLetterEntry.from_dict(json.loads(text)))
        return out

    async def count(self) -> int:
        return int(await self._r.llen(self._key))

    async def clear(self) -> None:
        await self._r.delete(self._key)


class InMemoryDeadLetterStore:
    def __init__(self, max_len: int = 1000) -> None:
        self._items: list[DeadLetterEntry] = []
        self._max = max_len

    async def push(self, entry: DeadLetterEntry) -> None:
        self._items.insert(0, entry)
        del self._items[self._max :]

    async def list(self, limit: int = 100) -> list[DeadLetterEntry]:
        return self._items[:limit]

    async def count(self) -> int:
        return len(self._items)

    async def clear(self) -> None:
        self._items.clear()
