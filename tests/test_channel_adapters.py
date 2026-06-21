"""Tests for WhatsApp / VK / Viber outbound adapters (mocked httpx transport)."""
from __future__ import annotations

import httpx
import pytest

from adapters.viber import ViberAdapter
from adapters.vk import VKAdapter
from adapters.whatsapp import WhatsAppAdapter


@pytest.fixture()
def mock_http(monkeypatch):
    """Patch httpx.AsyncClient so adapters talk to a MockTransport handler."""
    real = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(
            httpx, "AsyncClient",
            lambda **kw: real(
                transport=httpx.MockTransport(handler),
                **{k: v for k, v in kw.items() if k != "transport"},
            ),
        )
    return install


class TestWhatsApp:
    async def test_send_text(self, mock_http):
        seen = {}

        def handler(req):
            seen["url"] = str(req.url)
            seen["auth"] = req.headers.get("authorization")
            return httpx.Response(200, json={"messages": [{"id": "wamid.123"}]})

        mock_http(handler)
        out = await WhatsAppAdapter().send("PNID:ACCESS", "79990001122",
                                           {"content_type": "text", "text": "hi"})
        assert out["ok"] is True
        assert out["message_id"] == "wamid.123"
        assert "/PNID/messages" in seen["url"]
        assert seen["auth"] == "Bearer ACCESS"

    async def test_send_buttons(self, mock_http):
        captured = {}

        def handler(req):
            import json
            captured["body"] = json.loads(req.content)
            return httpx.Response(200, json={"messages": [{"id": "x"}]})

        mock_http(handler)
        out = await WhatsAppAdapter().send("P:A", "u", {
            "content_type": "buttons", "text": "pick",
            "buttons": [{"label": "Yes", "value": "y"}],
        })
        assert out["ok"] is True
        assert captured["body"]["type"] == "interactive"
        assert captured["body"]["interactive"]["action"]["buttons"][0]["reply"]["title"] == "Yes"


class TestVK:
    async def test_send_text(self, mock_http):
        def handler(req):
            return httpx.Response(200, json={"response": 555})

        mock_http(handler)
        out = await VKAdapter().send("grouptoken", "42", {"content_type": "text", "text": "hi"})
        assert out["ok"] is True
        assert out["message_id"] == "555"

    async def test_error_response(self, mock_http):
        def handler(req):
            return httpx.Response(200, json={"error": {"error_code": 5, "error_msg": "auth"}})

        mock_http(handler)
        out = await VKAdapter().send("bad", "42", {"text": "hi"})
        assert out["ok"] is False
        assert "error" in out


class TestViber:
    async def test_send_text(self, mock_http):
        def handler(req):
            assert req.headers.get("x-viber-auth-token") == "vtok"
            return httpx.Response(200, json={"status": 0, "message_token": "mt1"})

        mock_http(handler)
        out = await ViberAdapter().send("vtok", "user1", {"content_type": "text", "text": "hi"})
        assert out["ok"] is True
        assert out["message_id"] == "mt1"

    async def test_failure_status(self, mock_http):
        def handler(req):
            return httpx.Response(200, json={"status": 3, "status_message": "bad token"})

        mock_http(handler)
        out = await ViberAdapter().send("vtok", "user1", {"text": "hi"})
        assert out["ok"] is False


class TestRegistration:
    def test_all_channels_registered(self):
        from adapters import registry
        registry.load_all()
        for ch in ("telegram", "whatsapp", "vk", "viber"):
            assert registry.get(ch) is not None
