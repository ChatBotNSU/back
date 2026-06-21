"""Tests for encrypted secret store, API, and secret_ref resolution in handlers."""
from __future__ import annotations

import httpx

from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session
from services.secrets import Cipher
from stores.secret_store import InMemorySecretStore

load_all_handlers()


class TestCipher:
    def test_round_trip(self):
        c = Cipher()  # dev key
        token = c.encrypt("hello")
        assert token != "hello"
        assert c.decrypt(token) == "hello"


class TestSecretStore:
    async def test_put_get(self):
        store = InMemorySecretStore(Cipher())
        await store.put("ws1", "bitrix", {"base_url": "u", "token": "t"})
        assert await store.get_value("ws1", "bitrix") == {"base_url": "u", "token": "t"}

    async def test_encrypted_at_rest(self):
        cipher = Cipher()
        store = InMemorySecretStore(cipher)
        await store.put("ws1", "s", {"token": "supersecret"})
        # The raw stored blob must not contain the plaintext.
        raw = store._data[("ws1", "s")]
        assert "supersecret" not in raw

    async def test_workspace_isolation(self):
        store = InMemorySecretStore(Cipher())
        await store.put("ws1", "s", {"token": "a"})
        assert await store.get_value("ws2", "s") is None

    async def test_list_meta_hides_value(self):
        store = InMemorySecretStore(Cipher())
        await store.put("ws1", "s", {"token": "a"})
        meta = await store.list_meta("ws1")
        assert meta[0]["name"] == "s"
        assert "token" not in str(meta)
        assert "value" not in meta[0]

    async def test_delete(self):
        store = InMemorySecretStore(Cipher())
        await store.put("ws1", "s", {"token": "a"})
        assert await store.delete("ws1", "s") is True
        assert await store.delete("ws1", "s") is False


class TestSecretsAPI:
    def test_create_does_not_echo_value(self, client):
        resp = client.post("/api/secrets", json={
            "name": "my-bitrix", "value": {"token": "shh"},
        })
        assert resp.status_code == 201
        assert "value" not in resp.json()
        assert "shh" not in str(resp.json())

    def test_list_returns_meta_only(self, client):
        client.post("/api/secrets", json={"name": "s1", "value": {"token": "x"}})
        listed = client.get("/api/secrets").json()
        assert any(m["name"] == "s1" for m in listed)
        assert "x" not in str(listed)

    def test_delete(self, client):
        client.post("/api/secrets", json={"name": "s1", "value": {"token": "x"}})
        assert client.delete("/api/secrets/s1").status_code == 204
        assert client.delete("/api/secrets/s1").status_code == 404


class TestSecretRefInCrm:
    async def test_crm_resolves_creds_from_secret(self, secret_store):
        # Seed a credential bundle under the default workspace.
        await secret_store.put("default", "acme-bitrix", {
            "base_url": "https://acme.bitrix24.ru/rest/1/tok/",
        })

        def handler(req):
            assert "acme.bitrix24.ru" in str(req.url)
            return httpx.Response(200, json={"result": 99})

        crm = get(NodeType.CRM)
        out = await crm.execute(
            config={
                "provider": "bitrix24", "action": "create", "entity": "contact",
                "secret_ref": "acme-bitrix", "fields": {"NAME": "x"},
                "__client__": httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            },
            data_in={}, session=Session(flow_id="t"),
            node=Node(id="c", type=NodeType.CRM),
        )
        assert out["ok"] is True
        assert out["id"] == "99"
