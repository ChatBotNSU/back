"""Tests for Telegram setWebhook auto-registration on bot create/delete."""
from __future__ import annotations

import api.bots as bots_mod
import config


class _SpyAdapter:
    """Records set/delete webhook calls instead of hitting the network."""

    calls: list[tuple] = []

    async def set_webhook(self, token, url, secret=""):
        type(self).calls.append(("set", token, url, secret))
        return {"ok": True}

    async def delete_webhook(self, token):
        type(self).calls.append(("delete", token))
        return {"ok": True}


def _patch(monkeypatch, base_url):
    _SpyAdapter.calls = []
    monkeypatch.setattr(config.settings, "base_url", base_url)
    monkeypatch.setattr(bots_mod.settings, "base_url", base_url)
    # bots._sync imports adapters.telegram.TelegramAdapter lazily
    import adapters.telegram as tg
    monkeypatch.setattr(tg, "TelegramAdapter", _SpyAdapter)


class TestWebhookAutoRegister:
    def test_registers_on_create_when_base_url_set(self, client, monkeypatch):
        _patch(monkeypatch, "https://bots.example.com")
        resp = client.post(
            "/api/bots",
            json={"name": "B", "flow_id": "f1", "channel": "telegram", "token": "tok-9"},
        )
        assert resp.status_code == 201
        assert _SpyAdapter.calls == [
            ("set", "tok-9", "https://bots.example.com/webhook/telegram/tok-9", "")
        ]

    def test_skips_when_placeholder_base_url(self, client, monkeypatch):
        _patch(monkeypatch, "https://yourdomain.com")
        resp = client.post(
            "/api/bots",
            json={"name": "B", "flow_id": "f1", "channel": "telegram", "token": "tok-9"},
        )
        assert resp.status_code == 201
        assert _SpyAdapter.calls == []

    def test_skips_for_non_telegram(self, client, monkeypatch):
        _patch(monkeypatch, "https://bots.example.com")
        client.post(
            "/api/bots",
            json={"name": "W", "flow_id": "f1", "channel": "whatsapp", "token": "x"},
        )
        assert _SpyAdapter.calls == []

    def test_deletes_on_delete(self, client, monkeypatch):
        _patch(monkeypatch, "https://bots.example.com")
        created = client.post(
            "/api/bots",
            json={"name": "B", "flow_id": "f1", "channel": "telegram", "token": "tok-d"},
        ).json()
        _SpyAdapter.calls = []
        client.delete(f"/api/bots/{created['id']}")
        assert _SpyAdapter.calls == [("delete", "tok-d")]

    def test_create_succeeds_even_if_webhook_fails(self, client, monkeypatch):
        _patch(monkeypatch, "https://bots.example.com")

        async def boom(*a, **k):
            raise RuntimeError("telegram down")

        monkeypatch.setattr(_SpyAdapter, "set_webhook", boom)
        resp = client.post(
            "/api/bots",
            json={"name": "B", "flow_id": "f1", "channel": "telegram", "token": "t"},
        )
        assert resp.status_code == 201
