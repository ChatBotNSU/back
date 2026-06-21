"""Tests for /api/flows CRUD — uses SQLite + fakeredis via conftest."""
import pytest

SIMPLE_FLOW = {
    "name": "Test flow",
    "description": "A test",
    "nodes": [
        {
            "id": "n1",
            "type": "send_message",
            "label": "Hi",
            "config": {"text": "Hello"},
            "exec_out": {"conditions": [], "fallback": "n2"},
        },
        {
            "id": "n2",
            "type": "end",
            "label": "Done",
            "config": {},
        },
    ],
    "start_node": "n1",
}


class TestFlowCRUD:
    def test_create_flow(self, client):
        resp = client.post("/api/flows", json=SIMPLE_FLOW)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test flow"
        assert data["node_count"] == 2
        assert data["start_node"] == "n1"
        assert "id" in data

    def test_get_flow(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        resp = client.get(f"/api/flows/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_flow_not_found(self, client):
        resp = client.get("/api/flows/nonexistent")
        assert resp.status_code == 404

    def test_list_flows(self, client):
        client.post("/api/flows", json={**SIMPLE_FLOW, "name": "Flow A"})
        client.post("/api/flows", json={**SIMPLE_FLOW, "name": "Flow B"})
        resp = client.get("/api/flows")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_update_flow_name(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        resp = client.put(f"/api/flows/{created['id']}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["node_count"] == 2

    def test_update_flow_not_found(self, client):
        resp = client.put("/api/flows/ghost", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_flow(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        resp = client.delete(f"/api/flows/{created['id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/flows/{created['id']}").status_code == 404

    def test_validate_valid_flow(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        resp = client.post(f"/api/flows/{created['id']}/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        assert resp.json()["errors"] == []

    def test_validate_broken_goto(self, client):
        broken = {
            **SIMPLE_FLOW,
            "nodes": [
                {
                    "id": "n1",
                    "type": "send_message",
                    "config": {"text": "hi"},
                    "exec_out": {"conditions": [], "fallback": "ghost"},
                }
            ],
            "start_node": "n1",
        }
        created = client.post("/api/flows", json=broken).json()
        resp = client.post(f"/api/flows/{created['id']}/validate")
        assert resp.json()["valid"] is False
        assert any("ghost" in e for e in resp.json()["errors"])

    def test_validate_missing_start_node(self, client):
        no_start = {**SIMPLE_FLOW, "start_node": None}
        created = client.post("/api/flows", json=no_start).json()
        resp = client.post(f"/api/flows/{created['id']}/validate")
        assert resp.json()["valid"] is False

    def test_nodes_serialised_correctly(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        resp = client.get(f"/api/flows/{created['id']}")
        nodes = {n["id"]: n for n in resp.json()["nodes"]}
        assert nodes["n1"]["type"] == "send_message"
        assert nodes["n1"]["config"]["text"] == "Hello"
        assert nodes["n1"]["exec_out"]["fallback"] == "n2"


class TestFlowRun:
    def test_run_returns_bot_messages(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        resp = client.post(f"/api/flows/{created['id']}/run", json={"message": "hi"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "done"
        assert data["waiting"] is False
        assert any(m.get("text") == "Hello" for m in data["messages"])

    def test_run_waits_on_user_input(self, client):
        flow = {
            "name": "ask",
            "start_node": "q",
            "nodes": [
                {"id": "q", "type": "user_input", "config": {"variable": "name"},
                 "exec_out": {"conditions": [], "fallback": "e"}},
                {"id": "e", "type": "end", "config": {}},
            ],
        }
        created = client.post("/api/flows", json=flow).json()
        first = client.post(f"/api/flows/{created['id']}/run", json={"message": "start"}).json()
        assert first["waiting"] is True

        resumed = client.post(
            f"/api/flows/{created['id']}/run",
            json={"message": "Alice", "session_id": first["session_id"]},
        ).json()
        assert resumed["state"] == "done"

    def test_run_unknown_flow_404(self, client):
        assert client.post("/api/flows/ghost/run", json={"message": "x"}).status_code == 404


class TestFlowsUsage:
    def test_counts_bots_and_subgraph_refs(self, client):
        child = client.post("/api/flows", json={"name": "child", "nodes": [], "start_node": None}).json()
        # parent flow references child as a subgraph
        client.post("/api/flows", json={
            "name": "parent", "start_node": "s",
            "nodes": [
                {"id": "s", "type": "subgraph", "config": {"flow_id": child["id"]},
                 "exec_out": {"conditions": [], "fallback": "e"}},
                {"id": "e", "type": "end", "config": {}},
            ],
        })
        client.post("/api/bots", json={"name": "b", "flow_id": child["id"], "channel": "generic"})

        usage = client.get("/api/flows/usage").json()
        assert usage[child["id"]] == {"bots": 1, "subgraph_refs": 1}


class TestFlowVersions:
    def test_create_starts_at_v1(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        assert created["version"] == 1
        data = client.get(f"/api/flows/{created['id']}/versions").json()
        assert data["latest"] == 1
        assert [v["version"] for v in data["versions"]] == [1]

    def test_plain_save_does_not_add_version(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        # Editing + saving overwrites the draft without committing a version.
        client.put(f"/api/flows/{created['id']}", json={"name": "edited draft"})
        client.put(f"/api/flows/{created['id']}", json={"name": "edited again"})

        data = client.get(f"/api/flows/{created['id']}/versions").json()
        assert data["latest"] == 1
        assert [v["version"] for v in data["versions"]] == [1]

    def test_explicit_create_version_bumps(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        client.put(f"/api/flows/{created['id']}", json={"name": "v2 draft"})
        resp = client.post(f"/api/flows/{created['id']}/versions")
        assert resp.status_code == 201
        assert resp.json()["version"] == 2

        data = client.get(f"/api/flows/{created['id']}/versions").json()
        assert data["latest"] == 2
        assert [v["version"] for v in data["versions"]] == [2, 1]

    def test_create_version_unknown_flow_404(self, client):
        assert client.post("/api/flows/ghost/versions").status_code == 404

    def test_draft_dirty_tracks_uncommitted_changes(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        fid = created["id"]
        # Fresh flow: draft == v1.
        assert client.get(f"/api/flows/{fid}/versions").json()["draft_dirty"] is False
        # Edit the draft → differs from the latest version.
        client.put(f"/api/flows/{fid}", json={"name": "edited"})
        assert client.get(f"/api/flows/{fid}/versions").json()["draft_dirty"] is True
        # Commit → matches again.
        client.post(f"/api/flows/{fid}/versions")
        assert client.get(f"/api/flows/{fid}/versions").json()["draft_dirty"] is False
        # Saving identical content must not be a false positive.
        client.put(f"/api/flows/{fid}", json={"name": "edited"})
        assert client.get(f"/api/flows/{fid}/versions").json()["draft_dirty"] is False

    def test_versions_unknown_flow_404(self, client):
        assert client.get("/api/flows/ghost/versions").status_code == 404

    def test_version_snapshot_is_immutable(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        # Mutate the live draft after v1 was committed on create.
        client.put(f"/api/flows/{created['id']}", json={"name": "renamed draft"})

        v1 = client.get(f"/api/flows/{created['id']}/versions/1")
        assert v1.status_code == 200
        body = v1.json()
        assert body["version"] == 1
        assert body["name"] == "Test flow"  # original name, not "renamed draft"
        assert body["node_count"] == 2

    def test_get_version_missing_404(self, client):
        created = client.post("/api/flows", json=SIMPLE_FLOW).json()
        assert client.get(f"/api/flows/{created['id']}/versions/99").status_code == 404
        assert client.get("/api/flows/ghost/versions/1").status_code == 404
