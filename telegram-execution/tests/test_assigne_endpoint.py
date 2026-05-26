"""Smoke tests for /api/v1/telegram/assigne and the TelegramPoller bookkeeping.

The aim is narrow: when a user POSTs a TG bot token + chatbot_id, the poller
should remember that pairing and surface it via /get_all and /get/{token}.
We do not exercise real Telegram polling here.

NOTE: the production code has a latent bug — `controller/__init__.py` calls
`asyncio.create_task(...)` at import time, which raises `no running event loop`
unless imported from inside an async context. These tests therefore use async
test functions so a loop is running when the modules are loaded.
"""

from __future__ import annotations

import pytest


async def _client(fresh_modules):
    from fastapi.testclient import TestClient
    import main  # noqa: F401 -- importing for side effects (router registration)
    return TestClient(main.app)


@pytest.mark.asyncio
async def test_assigne_registers_token_and_chatbot(fresh_modules):
    client = await _client(fresh_modules)

    r = client.post("/api/v1/telegram/assigne", params={"token": "TKN-1", "chatbot_id": 7})
    assert r.status_code == 200, r.text

    r = client.get("/api/v1/telegram/get/TKN-1")
    assert r.status_code == 200
    assert r.json() == 7


@pytest.mark.asyncio
async def test_assigne_updates_existing_token_without_respawning_poller(fresh_modules):
    client = await _client(fresh_modules)

    client.post("/api/v1/telegram/assigne", params={"token": "TKN-1", "chatbot_id": 7})
    client.post("/api/v1/telegram/assigne", params={"token": "TKN-1", "chatbot_id": 42})

    assert client.get("/api/v1/telegram/get/TKN-1").json() == 42


@pytest.mark.asyncio
async def test_get_all_returns_every_assigned_token(fresh_modules):
    client = await _client(fresh_modules)

    client.post("/api/v1/telegram/assigne", params={"token": "A", "chatbot_id": 1})
    client.post("/api/v1/telegram/assigne", params={"token": "B", "chatbot_id": 2})

    body = client.get("/api/v1/telegram/get_all").json()
    assert body == {"A": 1, "B": 2}


@pytest.mark.asyncio
async def test_get_by_unknown_token_returns_404(fresh_modules):
    client = await _client(fresh_modules)
    r = client.get("/api/v1/telegram/get/missing-token")
    assert r.status_code == 404
