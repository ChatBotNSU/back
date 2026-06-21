"""Tests for Sheets / Calendar / Payment handlers (MockTransport + stub fallback)."""
from __future__ import annotations

import httpx

from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _run(node_type, config, session=None):
    h = get(node_type)
    return await h.execute(
        config=config, data_in={},
        session=session or Session(flow_id="t"),
        node=Node(id="n", type=node_type),
    )


class TestSheets:
    async def test_stub_without_provider(self):
        out = await _run(NodeType.SHEETS, {"action": "read"})
        assert out["stub"] is True

    async def test_google_read(self):
        def handler(req):
            assert "spreadsheets/sheet-1/values/A1:B2" in str(req.url)
            return httpx.Response(200, json={"values": [["a", "b"]]})

        out = await _run(NodeType.SHEETS, {
            "provider": "google", "action": "read", "spreadsheet_id": "sheet-1",
            "token": "tok", "range": "A1:B2", "__client__": _client(handler),
        })
        assert out["ok"] is True
        assert out["rows"] == [["a", "b"]]

    async def test_google_append(self):
        def handler(req):
            assert str(req.url).rstrip("?").endswith(":append") or ":append" in str(req.url)
            return httpx.Response(200, json={"updates": {"updatedRows": 1}})

        out = await _run(NodeType.SHEETS, {
            "provider": "google", "action": "append", "spreadsheet_id": "s1",
            "token": "tok", "range": "A1", "values": [["x"]], "__client__": _client(handler),
        })
        assert out["ok"] is True

    async def test_missing_creds_errors(self):
        out = await _run(NodeType.SHEETS, {"provider": "google", "spreadsheet_id": "s1"})
        assert out["ok"] is False
        assert "token" in out["error"]


class TestCalendar:
    async def test_stub_create(self):
        out = await _run(NodeType.CALENDAR, {"action": "create", "title": "Call"})
        assert out["stub"] is True
        assert out["event"]["title"] == "Call"

    async def test_google_create(self):
        def handler(req):
            assert req.method == "POST"
            return httpx.Response(200, json={"id": "ev-1"})

        out = await _run(NodeType.CALENDAR, {
            "provider": "google", "action": "create", "token": "tok",
            "title": "Meeting", "start": "2026-06-10T10:00:00Z",
            "end": "2026-06-10T11:00:00Z", "__client__": _client(handler),
        })
        assert out["ok"] is True
        assert out["event"]["id"] == "ev-1"

    async def test_calendly_slots(self):
        def handler(req):
            return httpx.Response(200, json={"collection": [
                {"scheduling_url": "https://calendly.com/x"}
            ]})

        out = await _run(NodeType.CALENDAR, {
            "provider": "calendly", "action": "slots", "token": "tok",
            "__client__": _client(handler),
        })
        assert out["slots"] == ["https://calendly.com/x"]


class TestPayment:
    async def test_stub_without_creds(self):
        out = await _run(NodeType.PAYMENT, {"provider": "stripe", "amount": 100})
        assert out["stub"] is True
        assert "stub-id" in out["payment_url"]

    async def test_stripe_checkout(self):
        def handler(req):
            assert str(req.url).endswith("/checkout/sessions")
            return httpx.Response(200, json={"id": "cs_1", "url": "https://pay.stripe/x"})

        out = await _run(NodeType.PAYMENT, {
            "provider": "stripe", "secret_key": "sk_test", "currency": "usd",
            "amount": 10, "__client__": _client(handler),
        })
        assert out["ok"] is True
        assert out["payment_url"] == "https://pay.stripe/x"
        assert out["payment_id"] == "cs_1"

    async def test_yookassa(self):
        def handler(req):
            return httpx.Response(200, json={
                "id": "p-1", "confirmation": {"confirmation_url": "https://yk/pay"}
            })

        out = await _run(NodeType.PAYMENT, {
            "provider": "yookassa", "shop_id": "shop", "secret_key": "key",
            "amount": 500, "currency": "RUB", "__client__": _client(handler),
        })
        assert out["ok"] is True
        assert out["payment_url"] == "https://yk/pay"
