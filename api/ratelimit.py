from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque


class SlidingWindowRateLimiter:
    """
    In-process sliding-window rate limiter.

    Tracks request timestamps per key and allows at most `max_requests` within
    the trailing `window` seconds. `max_requests <= 0` disables limiting.

    Single-process only; for multi-worker deployments back this with Redis.
    """

    def __init__(
        self,
        max_requests: int,
        window: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window = window
        self._clock = clock
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self.max_requests <= 0:
            return True
        now = self._clock()
        hits = self._hits[key]
        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True

    async def allow_async(self, key: str) -> bool:
        return self.allow(key)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


class RedisRateLimiter:
    """
    Distributed fixed-window rate limiter (INCR + EXPIRE).

    Shared across workers/processes via Redis. ``max_requests <= 0`` disables it.
    Fails open (allows) if Redis errors, so a Redis blip can't take webhooks down.
    """

    def __init__(self, redis: object, max_requests: int, window: int) -> None:
        self._r = redis
        self.max_requests = max_requests
        self.window = window

    def reset(self, key: str | None = None) -> None:
        # No-op: Redis keys expire on their own; provided for interface symmetry.
        return None

    async def allow_async(self, key: str) -> bool:
        if self.max_requests <= 0:
            return True
        bucket = f"rl:{key}"
        try:
            count = await self._r.incr(bucket)
            if count == 1:
                await self._r.expire(bucket, self.window)
            return count <= self.max_requests
        except Exception:  # noqa: BLE001 — never let limiter outages drop traffic
            return True
