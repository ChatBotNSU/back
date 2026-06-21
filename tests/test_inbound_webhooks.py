"""Tests for inbound parsing + /webhook/{channel}/{bot_id} routes."""
from __future__ import annotations

import pytest

from adapters import inbound
from models.flow import Flow
from models.node import Node, NodeType
from stores.bot_store import BotConfig

_FLOW = Flow(id="ch-flow", start_node="n1", nodes={"n1": Node(id="n1", type=NodeType.END)})


class TestParsers:
    def test_whatsapp_text(self):
        payload = {"entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Ann"}}],
            "messages": [{"from": "7999", "type": "text", "text": {"body": "hi"}}],
        }}]}]}
        out = inbound.parse("whatsapp", payload)
        assert out["user_id"] == "7999"
        assert out["text"] == "hi"
        assert out["user_meta"]["first_name"] == "Ann"

    def test_whatsapp_status_ignored(self):
        payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "sent"}]}}]}]}
        assert inbound.parse("whatsapp", payload) is None

    def test_vk_message(self):
        payload = {"type": "message_new", "object": {"message": {
            "from_id": 42, "peer_id": 42, "text": "yo"}}}
        out = inbound.parse("vk", payload)
        assert out["text"] == "yo"
        assert out["chat_id"] == "42"

    def test_vk_non_message_ignored(self):
        assert inbound.parse("vk", {"type": "group_join"}) is None

    def test_viber_message(self):
        payload = {"event": "message", "sender": {"id": "u1", "name": "Bob"},
                   "message": {"text": "hello"}}
        out = inbound.parse("viber", payload)
        assert out["user_id"] == "u1"
        assert out["text"] == "hello"

    def test_viber_non_message_ignored(self):
        assert inbound.parse("viber", {"event": "subscribed"}) is None


@pytest.fixture()
async def channel_bots(flow_store, bot_store):
    await flow_store.save(_FLOW)
    await bot_store.save(BotConfig(id="wa", name="w", flow_id="ch-flow", channel="whatsapp",
                                   token="P:A", metadata={"verify_token": "vt"}))
    await bot_store.save(BotConfig(id="vkb", name="v", flow_id="ch-flow", channel="vk",
                                   token="vktok", metadata={"vk_confirmation": "conf-xyz"}))
    await bot_store.save(BotConfig(id="vb", name="vb", flow_id="ch-flow", channel="viber",
                                   token="vbtok"))


class TestChannelWebhooks:
    def test_whatsapp_verify_challenge(self, client, channel_bots):
        resp = client.get("/webhook/whatsapp/wa", params={
            "hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "12345",
        })
        assert resp.status_code == 200
        assert resp.text == "12345"

    def test_whatsapp_verify_wrong_token(self, client, channel_bots):
        resp = client.get("/webhook/whatsapp/wa", params={
            "hub.mode": "subscribe", "hub.verify_token": "WRONG", "hub.challenge": "x",
        })
        assert resp.status_code == 403

    def test_whatsapp_inbound_message(self, client, channel_bots):
        payload = {"entry": [{"changes": [{"value": {
            "messages": [{"from": "7999", "type": "text", "text": {"body": "hi"}}],
        }}]}]}
        resp = client.post("/webhook/whatsapp/wa", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ok"] == "true"

    def test_vk_confirmation(self, client, channel_bots):
        resp = client.post("/webhook/vk/vkb", json={"type": "confirmation"})
        assert resp.status_code == 200
        assert resp.text == "conf-xyz"

    def test_vk_message_returns_ok(self, client, channel_bots):
        resp = client.post("/webhook/vk/vkb", json={
            "type": "message_new", "object": {"message": {"from_id": 1, "peer_id": 1, "text": "hi"}},
        })
        assert resp.status_code == 200
        assert resp.text == "ok"

    def test_viber_message(self, client, channel_bots):
        resp = client.post("/webhook/vb".replace("vb", "viber/vb"), json={
            "event": "message", "sender": {"id": "u1"}, "message": {"text": "hi"},
        })
        assert resp.status_code == 200

    def test_unknown_channel_404(self, client, channel_bots):
        resp = client.post("/webhook/signal/wa", json={"x": 1})
        assert resp.status_code == 404

    def test_channel_mismatch_404(self, client, channel_bots):
        # vkb is a VK bot; hitting it as whatsapp must 404.
        resp = client.post("/webhook/whatsapp/vkb", json={"entry": []})
        assert resp.status_code == 404
