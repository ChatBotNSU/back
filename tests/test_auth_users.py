"""Tests for user registration / login / JWT auth + workspace isolation by token."""
from __future__ import annotations

from api.auth import current_workspace, require_api_key
from services.security import create_token, decode_token, hash_password, verify_password


def _real_auth(client):
    """Drop the test auth bypass so real JWT/API-key resolution runs."""
    client.app.dependency_overrides.pop(require_api_key, None)
    client.app.dependency_overrides.pop(current_workspace, None)


class TestSecurityPrimitives:
    def test_password_round_trip(self):
        h = hash_password("hunter2")
        assert h != "hunter2"
        assert verify_password("hunter2", h)
        assert not verify_password("wrong", h)

    def test_jwt_round_trip(self):
        tok = create_token({"sub": "u1", "ws": "w1"})
        payload = decode_token(tok)
        assert payload and payload["sub"] == "u1" and payload["ws"] == "w1"

    def test_jwt_tampered_rejected(self):
        tok = create_token({"sub": "u1", "ws": "w1"})
        assert decode_token(tok + "x") is None


class TestAuthApi:
    def test_register_and_me(self, client):
        _real_auth(client)
        r = client.post("/api/auth/register", json={"email": "a@b.com", "password": "secret1"})
        assert r.status_code == 201
        body = r.json()
        assert body["user"]["email"] == "a@b.com"
        assert body["user"]["workspace_id"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == "a@b.com"

    def test_duplicate_email_409(self, client):
        _real_auth(client)
        client.post("/api/auth/register", json={"email": "dup@b.com", "password": "secret1"})
        r = client.post("/api/auth/register", json={"email": "dup@b.com", "password": "secret1"})
        assert r.status_code == 409

    def test_short_password_422(self, client):
        _real_auth(client)
        r = client.post("/api/auth/register", json={"email": "x@b.com", "password": "123"})
        assert r.status_code == 422

    def test_login(self, client):
        _real_auth(client)
        client.post("/api/auth/register", json={"email": "log@b.com", "password": "secret1"})
        ok = client.post("/api/auth/login", json={"email": "log@b.com", "password": "secret1"})
        assert ok.status_code == 200 and ok.json()["token"]
        bad = client.post("/api/auth/login", json={"email": "log@b.com", "password": "nope"})
        assert bad.status_code == 401

    def test_me_without_token_401(self, client):
        _real_auth(client)
        assert client.get("/api/auth/me").status_code == 401


class TestTokenScopesWorkspace:
    def test_flows_isolated_by_user(self, client):
        _real_auth(client)
        tok_a = client.post("/api/auth/register", json={"email": "ua@b.com", "password": "secret1"}).json()["token"]
        tok_b = client.post("/api/auth/register", json={"email": "ub@b.com", "password": "secret1"}).json()["token"]

        client.post("/api/flows", json={"name": "A flow", "nodes": [], "start_node": None},
                    headers={"Authorization": f"Bearer {tok_a}"})

        list_a = client.get("/api/flows", headers={"Authorization": f"Bearer {tok_a}"}).json()
        list_b = client.get("/api/flows", headers={"Authorization": f"Bearer {tok_b}"}).json()
        assert [f["name"] for f in list_a] == ["A flow"]
        assert list_b == []  # different user → different workspace → can't see A's flow
