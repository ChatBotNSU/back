"""Tests for Project CRUD + bot/flow scoping by project."""
from __future__ import annotations

from api.auth import current_workspace


def _as_ws(client, ws):
    client.app.dependency_overrides[current_workspace] = lambda: ws


class TestProjectCRUD:
    def test_create_and_get(self, client):
        created = client.post("/api/projects", json={"name": "Shop", "description": "store"}).json()
        assert created["name"] == "Shop"
        got = client.get(f"/api/projects/{created['id']}")
        assert got.status_code == 200
        assert got.json()["id"] == created["id"]

    def test_empty_name_422(self, client):
        assert client.post("/api/projects", json={"name": "  "}).status_code == 422

    def test_update(self, client):
        pid = client.post("/api/projects", json={"name": "A"}).json()["id"]
        resp = client.put(f"/api/projects/{pid}", json={"name": "B"})
        assert resp.json()["name"] == "B"

    def test_delete(self, client):
        pid = client.post("/api/projects", json={"name": "A"}).json()["id"]
        assert client.delete(f"/api/projects/{pid}").status_code == 204
        assert client.get(f"/api/projects/{pid}").status_code == 404

    def test_workspace_isolation(self, client):
        _as_ws(client, "ws-a")
        pid = client.post("/api/projects", json={"name": "A-proj"}).json()["id"]
        _as_ws(client, "ws-b")
        assert client.get(f"/api/projects/{pid}").status_code == 404
        assert pid not in [p["id"] for p in client.get("/api/projects").json()]


class TestProjectScoping:
    def test_flows_filtered_by_project(self, client):
        p1 = client.post("/api/projects", json={"name": "P1"}).json()["id"]
        p2 = client.post("/api/projects", json={"name": "P2"}).json()["id"]
        client.post("/api/flows", json={"name": "F1", "project_id": p1, "nodes": [], "start_node": None})
        client.post("/api/flows", json={"name": "F2", "project_id": p2, "nodes": [], "start_node": None})

        names_p1 = {f["name"] for f in client.get("/api/flows", params={"project_id": p1}).json()}
        assert names_p1 == {"F1"}

    def test_flow_carries_project_id(self, client):
        pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
        flow = client.post("/api/flows", json={"name": "F", "project_id": pid, "nodes": []}).json()
        assert flow["project_id"] == pid

    def test_bots_filtered_by_project(self, client):
        p1 = client.post("/api/projects", json={"name": "P1"}).json()["id"]
        client.post("/api/bots", json={"name": "B1", "flow_id": "f", "channel": "generic", "project_id": p1})
        client.post("/api/bots", json={"name": "B2", "flow_id": "f", "channel": "generic"})

        in_p1 = client.get("/api/bots", params={"project_id": p1}).json()
        assert [b["name"] for b in in_p1] == ["B1"]

    def test_bot_without_project_not_in_filter(self, client):
        p1 = client.post("/api/projects", json={"name": "P1"}).json()["id"]
        client.post("/api/bots", json={"name": "Loose", "flow_id": "f", "channel": "generic"})
        assert client.get("/api/bots", params={"project_id": p1}).json() == []
