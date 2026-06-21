"""Tests for project integrations: API, CRM-via-integration, and the sql node."""
from __future__ import annotations

import httpx

from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


class TestIntegrationsAPI:
    def _project(self, client):
        return client.post("/api/projects", json={"name": "P"}).json()["id"]

    def test_upsert_list_delete(self, client):
        pid = self._project(client)
        resp = client.post(f"/api/projects/{pid}/integrations", json={
            "name": "main-bitrix", "kind": "provider",
            "config": {"provider": "bitrix24", "secret_ref": "bx"},
        })
        assert resp.status_code == 201
        listed = client.get(f"/api/projects/{pid}/integrations").json()
        assert listed[0]["name"] == "main-bitrix"
        assert client.delete(f"/api/projects/{pid}/integrations/main-bitrix").status_code == 204

    def test_bad_kind_422(self, client):
        pid = self._project(client)
        resp = client.post(f"/api/projects/{pid}/integrations",
                           json={"name": "x", "kind": "weird", "config": {}})
        assert resp.status_code == 422

    def test_project_404(self, client):
        resp = client.post("/api/projects/ghost/integrations", json={"name": "x", "config": {}})
        assert resp.status_code == 404


class TestCrmViaIntegration:
    async def test_resolves_provider_and_secret(self, integration_store, secret_store):
        await secret_store.put("default", "bx", {"base_url": "https://acme.bitrix24.ru/rest/1/tok/"})
        await integration_store.put("P", "main-bitrix", "provider",
                                    {"provider": "bitrix24", "secret_ref": "bx"})

        def handler(req):
            assert "acme.bitrix24.ru" in str(req.url)
            return httpx.Response(200, json={"result": 77})

        crm = get(NodeType.CRM)
        out = await crm.execute(
            config={"integration": "main-bitrix", "action": "create", "entity": "contact",
                    "fields": {"NAME": "Ann"},
                    "__client__": httpx.AsyncClient(transport=httpx.MockTransport(handler))},
            data_in={}, session=Session(flow_id="f", project_id="P"),
            node=Node(id="c", type=NodeType.CRM),
        )
        assert out["ok"] is True
        assert out["id"] == "77"


class TestSqlNode:
    async def _make_db(self, tmp_path):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        dsn = f"sqlite+aiosqlite:///{tmp_path/'ext.db'}"
        engine = create_async_engine(dsn)
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
            await conn.execute(text("INSERT INTO t (id, name) VALUES (1, 'Alice')"))
        await engine.dispose()
        return dsn

    async def test_select_via_connection(self, tmp_path, integration_store):
        dsn = await self._make_db(tmp_path)
        await integration_store.put("P", "mydb", "db", {"dsn": dsn})

        sql = get(NodeType.SQL)
        out = await sql.execute(
            config={"connection": "mydb", "sql": "SELECT name FROM t WHERE id = :id",
                    "params": {"id": 1}, "output_var": "rows"},
            data_in={}, session=Session(flow_id="f", project_id="P"),
            node=Node(id="s", type=NodeType.SQL),
        )
        assert out["ok"] is True
        assert out["rows"] == [{"name": "Alice"}]

    async def test_no_dsn_errors(self, integration_store):
        sql = get(NodeType.SQL)
        out = await sql.execute(
            config={"sql": "SELECT 1"}, data_in={},
            session=Session(flow_id="f", project_id="P"), node=Node(id="s", type=NodeType.SQL),
        )
        assert out["ok"] is False
