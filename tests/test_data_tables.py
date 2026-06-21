"""Tests for built-in data tables (API + database node handler)."""
from __future__ import annotations

from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


class TestDataTablesAPI:
    def _project(self, client):
        return client.post("/api/projects", json={"name": "P"}).json()["id"]

    def test_insert_and_list(self, client):
        pid = self._project(client)
        rec = client.post(f"/api/projects/{pid}/tables/clients/records",
                          json={"data": {"name": "Ann", "phone": "111"}})
        assert rec.status_code == 201
        assert rec.json()["data"]["name"] == "Ann"

        listed = client.get(f"/api/projects/{pid}/tables/clients/records").json()
        assert listed["count"] == 1

    def test_query_filter(self, client):
        pid = self._project(client)
        client.post(f"/api/projects/{pid}/tables/c/records", json={"data": {"name": "A", "city": "Moscow"}})
        client.post(f"/api/projects/{pid}/tables/c/records", json={"data": {"name": "B", "city": "Kazan"}})
        resp = client.post(f"/api/projects/{pid}/tables/c/records/query", json={"where": {"city": "Kazan"}})
        recs = resp.json()["records"]
        assert len(recs) == 1 and recs[0]["data"]["name"] == "B"

    def test_get_update_delete(self, client):
        pid = self._project(client)
        rid = client.post(f"/api/projects/{pid}/tables/t/records", json={"data": {"x": 1}}).json()["id"]
        assert client.get(f"/api/projects/{pid}/tables/t/records/{rid}").json()["data"]["x"] == 1
        upd = client.put(f"/api/projects/{pid}/tables/t/records/{rid}", json={"data": {"x": 2}})
        assert upd.json()["data"]["x"] == 2
        assert client.delete(f"/api/projects/{pid}/tables/t/records/{rid}").status_code == 204
        assert client.get(f"/api/projects/{pid}/tables/t/records/{rid}").status_code == 404

    def test_list_tables(self, client):
        pid = self._project(client)
        client.post(f"/api/projects/{pid}/tables/a/records", json={"data": {}})
        client.post(f"/api/projects/{pid}/tables/b/records", json={"data": {}})
        assert set(client.get(f"/api/projects/{pid}/tables").json()["tables"]) == {"a", "b"}

    def test_unknown_project_404(self, client):
        assert client.get("/api/projects/ghost/tables").status_code == 404


class TestDatabaseNode:
    async def _run(self, config, session):
        h = get(NodeType.DATABASE)
        return await h.execute(config=config, data_in={}, session=session,
                               node=Node(id="d", type=NodeType.DATABASE))

    async def test_insert_then_query(self, data_store):
        session = Session(flow_id="f", project_id="proj-1", variables={"phone": "777"})
        ins = await self._run(
            {"action": "insert", "table": "leads", "data": {"phone": "{{phone}}", "status": "new"}},
            session,
        )
        assert ins["ok"] is True
        assert ins["record"]["data"]["phone"] == "777"

        q = await self._run(
            {"action": "query", "table": "leads", "where": {"phone": "{{phone}}"},
             "output_var": "found"},
            session,
        )
        assert q["count"] == 1
        assert session.variables["found"][0]["data"]["status"] == "new"

    async def test_no_project_returns_error(self, data_store):
        session = Session(flow_id="f")  # project_id empty
        out = await self._run({"action": "query", "table": "x"}, session)
        assert out["ok"] is False

    async def test_update_and_delete(self, data_store):
        session = Session(flow_id="f", project_id="p")
        rid = (await self._run({"action": "insert", "table": "t", "data": {"n": 1}}, session))["record"]["id"]
        upd = await self._run({"action": "update", "table": "t", "record_id": rid, "data": {"n": 2}}, session)
        assert upd["record"]["data"]["n"] == 2
        dele = await self._run({"action": "delete", "table": "t", "record_id": rid}, session)
        assert dele["ok"] is True
