"""Tests for Salesforce CRM, AmoCRM token refresh, Tinkoff payment."""
from __future__ import annotations

import httpx

import pytest

from integrations.crm import AmoCrmProvider, build_provider as build_crm
from integrations.payment import PaymentError, build_provider as build_pay


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestSalesforce:
    async def test_create(self):
        def handler(req):
            assert req.url.path.endswith("/sobjects/Contact")
            assert req.headers["authorization"] == "Bearer tok"
            return httpx.Response(201, json={"id": "003X", "success": True})

        prov = build_crm("salesforce", {
            "base_url": "https://acme.my.salesforce.com", "token": "tok",
            "__client__": None,
        }, client=_client(handler))
        out = await prov.execute("create", "contact", {"LastName": "Ann"})
        assert out["ok"] is True
        assert out["id"] == "003X"

    async def test_find(self):
        def handler(req):
            assert "/query" in req.url.path
            return httpx.Response(200, json={"records": [{"Id": "003Y"}]})

        prov = build_crm("salesforce",
                         {"base_url": "https://x.salesforce.com", "token": "t"},
                         client=_client(handler))
        out = await prov.execute("find", "contact", {"Email": "a@b.c"})
        assert out["found"] is True
        assert out["id"] == "003Y"


class TestAmoCrmRefresh:
    async def test_refresh_on_401_then_retry(self):
        state = {"calls": 0}

        def handler(req):
            if req.url.path.endswith("/oauth2/access_token"):
                return httpx.Response(200, json={"access_token": "newtok", "refresh_token": "r2"})
            state["calls"] += 1
            if state["calls"] == 1:
                return httpx.Response(401, json={"title": "Unauthorized"})
            assert req.headers["authorization"] == "Bearer newtok"
            return httpx.Response(200, json={"_embedded": {"contacts": [{"id": 7}]}})

        prov = AmoCrmProvider(
            "https://acme.amocrm.ru", "oldtok", client=_client(handler),
            refresh={"refresh_token": "r1", "client_id": "c", "client_secret": "s"},
        )
        out = await prov.execute("find", "contact", {"query": "Ann"})
        assert out["ok"] is True
        assert out["id"] == "7"
        assert out["refreshed_token"] == "newtok"
        assert prov.token == "newtok"

    async def test_no_refresh_creds_no_retry(self):
        def handler(req):
            return httpx.Response(401, json={})

        prov = AmoCrmProvider("https://acme.amocrm.ru", "oldtok", client=_client(handler))
        out = await prov.execute("find", "contact", {"query": "x"})
        assert out["ok"] is False


class TestTinkoff:
    async def test_create_payment_signed(self):
        captured = {}

        def handler(req):
            import json
            captured["body"] = json.loads(req.content)
            assert req.url.path.endswith("/v2/Init")
            return httpx.Response(200, json={
                "Success": True, "PaymentId": "9001", "PaymentURL": "https://pay.tinkoff/x",
            })

        prov = build_pay("tinkoff",
                         {"terminal_key": "TERM", "secret_key": "pass"},
                         client=_client(handler))
        out = await prov.create_payment(500, "RUB", "Order #1", "")
        assert out["ok"] is True
        assert out["payment_url"] == "https://pay.tinkoff/x"
        assert out["payment_id"] == "9001"
        # Signature token must be present and amount in kopecks.
        assert "Token" in captured["body"]
        assert captured["body"]["Amount"] == 50000

    def test_missing_creds_raises(self):
        with pytest.raises(PaymentError):
            build_pay("tinkoff", {"terminal_key": "T"})  # no secret_key/password
