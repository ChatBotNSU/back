"""Tests for channel adapter registry and send_message integration."""
import pytest

from adapters import registry as adapter_registry
from adapters.base import ChannelAdapter
from models.node import Node, NodeType
from models.session import Session


def make_session(**kw) -> Session:
    return Session(flow_id="f1", **kw)


def make_node(config: dict) -> Node:
    return Node(id="n1", type=NodeType.SEND_MESSAGE, config=config)


# ─── Mock adapter ─────────────────────────────────────────────────────────────

class MockAdapter:
    channel = "mock"
    sent: list = []

    async def send(self, token, recipient, message):
        self.sent.append({"token": token, "to": recipient, "msg": message})
        return {"ok": True, "message_id": "mock-msg-1"}


# ─── Registry ─────────────────────────────────────────────────────────────────

class TestAdapterRegistry:
    def test_register_and_get(self):
        mock = MockAdapter()
        adapter_registry.register(mock)
        got = adapter_registry.get("mock")
        assert got is mock

    def test_get_unknown_returns_none(self):
        assert adapter_registry.get("nonexistent-channel-xyz") is None

    async def test_send_via_registry(self):
        mock = MockAdapter()
        mock.sent = []
        adapter_registry.register(mock)
        result = await adapter_registry.send("mock", "tok", "u1", {"content_type": "text", "text": "hi"})
        assert result["ok"] is True
        assert len(mock.sent) == 1

    async def test_send_missing_adapter(self):
        result = await adapter_registry.send("no-adapter-xyz", "tok", "u1", {})
        assert result["ok"] is False
        assert "error" in result


# ─── send_message integration ─────────────────────────────────────────────────

class TestSendMessageWithAdapter:
    async def test_delivers_via_adapter(self):
        from engine.registry import load_all_handlers
        load_all_handlers()

        mock = MockAdapter()
        mock.sent = []
        adapter_registry.register(mock)

        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        session.variables["channel"] = "mock"
        session.variables["chat_id"] = "chat-99"
        session.variables["__bot_token__"] = "tok-123"

        out = await h.execute({"text": "Hello"}, {}, session, make_node({}))
        assert out["delivered"] is True
        assert out["message_id"] == "mock-msg-1"
        assert len(mock.sent) == 1
        assert mock.sent[0]["to"] == "chat-99"

    async def test_no_channel_skips_delivery(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        # No channel / chat_id in session
        out = await h.execute({"text": "Hello"}, {}, session, make_node({}))
        # Should not crash, delivered=False
        assert out["delivered"] is False

    async def test_template_still_rendered_without_adapter(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        session.variables["name"] = "Bob"
        out = await h.execute({"text": "Hi {{name}}!"}, {}, session, make_node({}))
        assert out["message"]["text"] == "Hi Bob!"
