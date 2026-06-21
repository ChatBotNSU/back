"""Tests for security hardening: API-key hashing, CORS, webhook auth, Redis rate limit."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from api.ratelimit import RedisRateLimiter
from config import Settings
from models.flow import Flow
from models.node import Node, NodeType
from stores.bot_store import BotConfig

# ─── API key hashing + constant-time match ─────────────────────────────────────

class TestApiKeyAuth:
    def test_plain_key_with_workspace(self):
        s = Settings(api_keys="plainkey:wsA")
        assert s.is_valid_api_key("plainkey") is True
        assert s.is_valid_api_key("nope") is False
        assert s.workspace_for_key("plainkey") == "wsA"

    def test_hashed_key(self):
        digest = hashlib.sha256(b"mykey").hexdigest()
        s = Settings(api_keys=f"sha256:{digest}:wsB")
        assert s.is_valid_api_key("mykey") is True
        assert s.is_valid_api_key("wrong") is False
        assert s.workspace_for_key("mykey") == "wsB"

    def test_dev_mode_allows_all(self):
        s = Settings(api_keys="")
        assert s.is_valid_api_key("whatever") is True
        assert s.workspace_for_key("whatever") == "default"


class TestCors:
    def test_list_parsing(self):
        assert Settings(cors_origins="https://a.com, https://b.com").cors_origin_list() == [
            "https://a.com", "https://b.com",
        ]

    def test_wildcard_default(self):
        assert Settings(cors_origins="*").cors_origin_list() == ["*"]


# ─── Redis rate limiter ────────────────────────────────────────────────────────

class TestRedisRateLimiter:
    async def test_fixed_window(self, redis_client):
        rl = RedisRateLimiter(redis_client, max_requests=2, window=60)
        assert await rl.allow_async("k") is True
        assert await rl.allow_async("k") is True
        assert await rl.allow_async("k") is False

    async def test_disabled(self, redis_client):
        rl = RedisRateLimiter(redis_client, max_requests=0, window=60)
        assert all([await rl.allow_async("k") for _ in range(50)])

    async def test_fails_open_on_redis_error(self):
        class Broken:
            async def incr(self, *a):
                raise RuntimeError("redis down")
        rl = RedisRateLimiter(Broken(), max_requests=1, window=60)
        assert await rl.allow_async("k") is True  # fail-open


# ─── Webhook auth ──────────────────────────────────────────────────────────────

_FLOW = Flow(id="sec-flow", start_node="n1", nodes={"n1": Node(id="n1", type=NodeType.END)})


@pytest.fixture()
async def secured_bots(flow_store, bot_store):
    await flow_store.save(_FLOW)
    await bot_store.save(BotConfig(
        id="tg-bot", name="t", flow_id="sec-flow", channel="telegram",
        token="tok-sec", webhook_secret="shh",
    ))
    await bot_store.save(BotConfig(
        id="gen-bot", name="g", flow_id="sec-flow", channel="generic",
        webhook_secret="shh",
    ))
    await bot_store.save(BotConfig(
        id="open-bot", name="o", flow_id="sec-flow", channel="telegram",
        token="tok-open",  # no secret
    ))


TG_UPDATE = {"update_id": 1, "message": {"from": {"id": 5}, "chat": {"id": 5}, "text": "hi"}}


class TestTelegramSecret:
    def test_valid_secret_accepted(self, client, secured_bots):
        resp = client.post(
            "/webhook/telegram/tok-sec", json=TG_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "shh"},
        )
        assert resp.status_code == 200

    def test_wrong_secret_rejected(self, client, secured_bots):
        resp = client.post(
            "/webhook/telegram/tok-sec", json=TG_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
        )
        assert resp.status_code == 403

    def test_missing_secret_rejected(self, client, secured_bots):
        resp = client.post("/webhook/telegram/tok-sec", json=TG_UPDATE)
        assert resp.status_code == 403

    def test_bot_without_secret_accepts(self, client, secured_bots):
        resp = client.post("/webhook/telegram/tok-open", json=TG_UPDATE)
        assert resp.status_code == 200


class TestGenericSignature:
    def _sig(self, body: bytes) -> str:
        return hmac.new(b"shh", body, hashlib.sha256).hexdigest()

    def test_valid_signature_accepted(self, client, secured_bots):
        body = json.dumps({"user_id": "u1", "text": "hi"}).encode()
        resp = client.post(
            "/webhook/generic/gen-bot", content=body,
            headers={"X-Signature": self._sig(body), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    def test_invalid_signature_rejected(self, client, secured_bots):
        body = json.dumps({"user_id": "u1", "text": "hi"}).encode()
        resp = client.post(
            "/webhook/generic/gen-bot", content=body,
            headers={"X-Signature": "deadbeef", "Content-Type": "application/json"},
        )
        assert resp.status_code == 403
