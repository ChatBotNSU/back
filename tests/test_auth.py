"""Tests for API key authentication."""
import pytest
from fastapi.testclient import TestClient

from main import create_app
from api.deps import get_flow_store, get_session_store, get_bot_store
from stores.flow_store import InMemoryFlowStore
from stores.session_store import InMemorySessionStore
from stores.bot_store import InMemoryBotStore


@pytest.fixture()
def auth_client():
    """Client WITHOUT auth bypass — uses real auth logic."""
    import config as cfg
    original = cfg.settings.api_keys

    cfg.settings.api_keys = "valid-key-1,valid-key-2"

    app = create_app()
    app.dependency_overrides[get_flow_store] = lambda: InMemoryFlowStore()
    app.dependency_overrides[get_session_store] = lambda: InMemorySessionStore()
    app.dependency_overrides[get_bot_store] = lambda: InMemoryBotStore()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    cfg.settings.api_keys = original


class TestAuthRequired:
    def test_no_key_returns_401(self, auth_client):
        resp = auth_client.get("/api/flows")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, auth_client):
        resp = auth_client.get("/api/flows", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_valid_key_passes(self, auth_client):
        resp = auth_client.get("/api/flows", headers={"X-API-Key": "valid-key-1"})
        assert resp.status_code == 200

    def test_second_valid_key_passes(self, auth_client):
        resp = auth_client.get("/api/flows", headers={"X-API-Key": "valid-key-2"})
        assert resp.status_code == 200

    def test_webhook_requires_no_key(self, auth_client):
        """Webhooks stay public — Telegram authenticates via bot token in URL."""
        resp = auth_client.post("/webhook/telegram/any-token", json={"update_id": 1})
        assert resp.status_code == 200

    def test_health_requires_no_key(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200


class TestAuthDisabled:
    def test_no_key_passes_when_api_keys_empty(self, client):
        """When API_KEYS env is empty, auth is disabled (dev mode)."""
        resp = client.get("/api/flows")
        assert resp.status_code == 200
