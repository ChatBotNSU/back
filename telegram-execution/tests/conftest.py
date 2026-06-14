"""Test fixtures for telegram-execution.

The service is awkward to import in isolation because:
- `controller/__init__.py` instantiates RedisStreamsController() and then calls
  `asyncio.create_task(...)` at import time, which requires a running loop.
- `poller/__init__.py` instantiates TelegramPoller() at import time.
- `sender/__init__.py` instantiates TelegramResponseSender() at import time.
- `api/telegram_api.py` instantiates `poller = TelegramPoller()` at module load.

For unit tests we shim Redis and aiogram before any backend module loads, and
neutralize the polling spawn so tokens stay registered for the duration of the
test.
"""

from __future__ import annotations
"""Pytest configuration for telegram-execution tests."""

import sys
from pathlib import Path

import pytest
from unittest.mock import MagicMock

# Make src/ importable.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def fresh_modules(monkeypatch):
    """Drop cached backend modules so each test gets a clean singleton state."""
    # 1. Stub redis.asyncio.Redis — used by controller/redis.py.
    import redis.asyncio as redis_asyncio

    class _FakeRedis:
        def __init__(self, *args, **kwargs):
            self.stream = []

        async def xadd(self, stream, payload):
            self.stream.append((stream, payload))
            return b"0-0"

        async def xreadgroup(self, *args, **kwargs):
            return []

        async def xgroup_create(self, *args, **kwargs):
            return True

    monkeypatch.setattr(redis_asyncio, "Redis", _FakeRedis)

    # 2. Stub aiogram.Bot and Dispatcher.
    import aiogram
    from aiogram import types

    class _StubBot:
        def __init__(self, token, **kwargs):
            self.token = token

    class _StubDispatcher:
        def __init__(self, *args, **kwargs):
            self.handlers = []
            self._message_decorator = MagicMock()
            self._callback_decorator = MagicMock()

        def message(self):
            def decorator(fn):
                self.handlers.append(fn)
                return fn
            return self._message_decorator

        def callback_query(self):
            def decorator(fn):
                self.handlers.append(fn)
                return fn
            return self._callback_decorator

        def resolve_used_update_types(self):
            return []

        async def start_polling(self, *args, **kwargs):
            return None

    class _StubCallbackQuery:
        pass

    monkeypatch.setattr(aiogram, "Bot", _StubBot)
    monkeypatch.setattr(aiogram, "Dispatcher", _StubDispatcher)
    monkeypatch.setattr(types, "CallbackQuery", _StubCallbackQuery)

    # 3. The production code has a latent bug: `controller/__init__.py` calls
    # `asyncio.create_task(...)` at module-import time, which fails outside a
    # running loop. Stub `asyncio.create_task` during the import phase so the
    # module can load. The stubbed coroutine is closed to avoid the
    # "coroutine was never awaited" warning.
    import asyncio

    def _noop_create_task(coro, *args, **kwargs):
        try:
            coro.close()
        except Exception:
            pass
        return None

    monkeypatch.setattr(asyncio, "create_task", _noop_create_task)

    # 4. Drop cached modules so re-import picks up the stubs.
    for name in list(sys.modules):
        if name.startswith(("api", "controller", "poller", "sender", "models", "config", "main")):
            sys.modules.pop(name, None)

    # 5. Pre-import poller.telegram_poller and neutralize `_poll_bot` so it
    # does not actually spawn a polling task. The real method would, on early
    # exit, remove the token from `_bots` and our /get endpoints would 404.
    import poller.telegram_poller as tp_mod

    async def _noop_poll(self, token):
        return None

    monkeypatch.setattr(tp_mod.TelegramPoller, "_poll_bot", _noop_poll)

    yield

    # 6. Cleanup after the test.
    for name in list(sys.modules):
        if name.startswith(("api", "controller", "poller", "sender", "models", "config", "main")):
            sys.modules.pop(name, None)
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
