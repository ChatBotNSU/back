"""Tests for CRM providers + handler routing (httpx.MockTransport, no network)."""
from __future__ import annotations

import httpx
import pytest

from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _run(config, session=None):
    h = get(NodeType.CRM)
    return await h.execute(
        config=config, data_in={},
        session=session or Session(flow_id="t"),
        node=Node(id="c", type=NodeType.CRM),
    )


class TestStubFallback:
    async def test_no_provider_returns_stub(self):
        out = await _run({"provider": "", "action": "find", "entity": "contact"})
        assert out["stub"] is True
        assert out["found"] is True

    async def test_unknown_provider_returns_stub(self):
        out = await _run({"provider": "zoho", "action": "create"})
        assert out["stub"] is True
        assert out["created"] is True


class TestBitrix24:
    async def test_create(self):
        def handler(req):
            assert req.url.path.endswith("crm.contact.add.json")
            return httpx.Response(200, json={"result": 42})

        out = await _run({
            "provider": "bitrix24", "action": "create", "entity": "contact",
            "base_url": "https://acme.bitrix24.ru/rest/1/tok/",
            "fields": {"NAME": "{{name}}"}, "__client__": _client(handler),
        }, session=Session(flow_id="t", variables={"name": "Alice"}))
        assert out["ok"] is True
        assert out["id"] == "42"

    async def test_find(self):
        def handler(req):
            assert req.url.path.endswith("crm.contact.list.json")
            return httpx.Response(200, json={"result": [{"ID": "7"}]})

        out = await _run({
            "provider": "bitrix24", "action": "find", "entity": "contact",
            "base_url": "https://acme.bitrix24.ru/rest/1/tok/",
            "fields": {"PHONE": "123"}, "__client__": _client(handler),
        })
        assert out["found"] is True
        assert out["id"] == "7"

    async def test_missing_base_url_errors(self):
        out = await _run({"provider": "bitrix24", "action": "find"})
        assert out["ok"] is False
        assert "base_url" in out["error"]

    async def test_transport_error_is_caught(self):
        def handler(req):
            raise httpx.ConnectError("boom")

        out = await _run({
            "provider": "bitrix24", "action": "find", "entity": "contact",
            "base_url": "https://acme.bitrix24.ru/rest/1/tok/",
            "__client__": _client(handler),
        })
        assert out["ok"] is False
        assert "error" in out


class TestHubSpot:
    async def test_create(self):
        def handler(req):
            assert req.url.path == "/crm/v3/objects/contacts"
            assert req.headers["authorization"] == "Bearer tok-1"
            return httpx.Response(201, json={"id": "abc123"})

        out = await _run({
            "provider": "hubspot", "action": "create", "entity": "contact",
            "token": "tok-1", "fields": {"email": "a@b.c"},
            "__client__": _client(handler),
        })
        assert out["ok"] is True
        assert out["id"] == "abc123"


class TestAmoCrm:
    async def test_find(self):
        def handler(req):
            assert req.url.path == "/api/v4/contacts"
            return httpx.Response(200, json={"_embedded": {"contacts": [{"id": 5}]}})

        out = await _run({
            "provider": "amocrm", "action": "find", "entity": "contact",
            "base_url": "https://acme.amocrm.ru", "token": "t",
            "fields": {"query": "Alice"}, "__client__": _client(handler),
        })
        assert out["found"] is True
        assert out["id"] == "5"
