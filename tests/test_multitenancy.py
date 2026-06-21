"""Tests for workspace isolation (multitenancy via API-key → workspace)."""
from __future__ import annotations

import pytest

from api.auth import current_workspace
from config import Settings


def _as_workspace(client, ws: str):
    """Make subsequent requests on `client` run as workspace `ws`."""
    client.app.dependency_overrides[current_workspace] = lambda: ws


class TestConfigKeyMapping:
    def test_plain_keys_default_workspace(self):
        s = Settings(api_keys="k1,k2")
        assert s.is_valid_api_key("k1") is True
        assert s.workspace_for_key("k1") == "default"

    def test_key_workspace_mapping(self):
        s = Settings(api_keys="secret1:acme, secret2:globex")
        assert s.workspace_for_key("secret1") == "acme"
        assert s.workspace_for_key("secret2") == "globex"
        assert s.is_valid_api_key("secret1") is True
        assert s.is_valid_api_key("nope") is False

    def test_dev_mode_defaults(self):
        s = Settings(api_keys="")
        assert s.workspace_for_key("anything") == "default"


class TestFlowIsolation:
    def test_flow_not_visible_across_workspaces(self, client):
        _as_workspace(client, "ws-a")
        created = client.post("/api/flows", json={
            "name": "A-flow",
            "nodes": [{"id": "n1", "type": "end", "config": {}}],
            "start_node": "n1",
        }).json()

        # Same workspace sees it.
        assert client.get(f"/api/flows/{created['id']}").status_code == 200

        # Different workspace does not.
        _as_workspace(client, "ws-b")
        assert client.get(f"/api/flows/{created['id']}").status_code == 404
        assert created["id"] not in [f["id"] for f in client.get("/api/flows").json()]

    def test_cannot_delete_other_workspace_flow(self, client):
        _as_workspace(client, "ws-a")
        created = client.post("/api/flows", json={
            "name": "A", "nodes": [{"id": "n1", "type": "end", "config": {}}],
            "start_node": "n1",
        }).json()

        _as_workspace(client, "ws-b")
        assert client.delete(f"/api/flows/{created['id']}").status_code == 404

        _as_workspace(client, "ws-a")
        assert client.get(f"/api/flows/{created['id']}").status_code == 200

    def test_list_scoped_per_workspace(self, client):
        _as_workspace(client, "ws-a")
        client.post("/api/flows", json={"name": "A1", "nodes": [], "start_node": None})
        _as_workspace(client, "ws-b")
        client.post("/api/flows", json={"name": "B1", "nodes": [], "start_node": None})

        names_b = {f["name"] for f in client.get("/api/flows").json()}
        assert "B1" in names_b and "A1" not in names_b


class TestBotIsolation:
    def test_bot_not_visible_across_workspaces(self, client):
        _as_workspace(client, "ws-a")
        bot = client.post("/api/bots", json={
            "name": "A-bot", "flow_id": "f1", "channel": "generic",
        }).json()

        _as_workspace(client, "ws-b")
        assert client.get(f"/api/bots/{bot['id']}").status_code == 404

        _as_workspace(client, "ws-a")
        assert client.get(f"/api/bots/{bot['id']}").status_code == 200
