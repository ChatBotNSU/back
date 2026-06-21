"""Tests for AI flow generation / improvement endpoints.

The LLM call is isolated in `services.llm.acomplete`; we monkeypatch it so no
network/litellm is needed.
"""
from __future__ import annotations

import json

import pytest

import services.llm as llm_mod

VALID_FLOW_JSON = {
    "name": "Приветствие",
    "description": "Здоровается и завершает диалог",
    "start_node": "t1",
    "nodes": [
        {
            "id": "t1",
            "type": "message_trigger",
            "label": "Старт",
            "config": {},
            "exec_out": {"conditions": [], "fallback": "m1"},
        },
        {
            "id": "m1",
            "type": "send_message",
            "label": "Привет",
            "config": {"text": "Привет!"},
            "exec_out": {"conditions": [], "fallback": "e1"},
        },
        {"id": "e1", "type": "end", "label": "Конец", "config": {}},
    ],
}

BROKEN_FLOW_JSON = {
    **VALID_FLOW_JSON,
    "nodes": [
        {
            "id": "t1",
            "type": "message_trigger",
            "config": {},
            "exec_out": {"conditions": [], "fallback": "ghost"},
        }
    ],
}


def _scripted(*responses: str):
    """Return an async fake acomplete yielding successive responses."""
    calls = {"n": 0}

    async def fake_acomplete(model, messages, temperature=0.7, response_format=None):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[i]

    fake_acomplete.calls = calls  # type: ignore[attr-defined]
    return fake_acomplete


class TestGenerateFlow:
    def test_generate_valid(self, client, monkeypatch):
        monkeypatch.setattr(llm_mod, "acomplete", _scripted(json.dumps(VALID_FLOW_JSON)))
        resp = client.post("/api/flows/generate", json={"prompt": "бот-приветствие"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["node_count"] == 3
        assert data["start_node"] == "t1"
        # persisted by default
        assert client.get(f"/api/flows/{data['id']}").status_code == 200

    def test_generate_no_save(self, client, monkeypatch):
        monkeypatch.setattr(llm_mod, "acomplete", _scripted(json.dumps(VALID_FLOW_JSON)))
        resp = client.post(
            "/api/flows/generate", json={"prompt": "x", "save": False}
        )
        assert resp.status_code == 201
        assert client.get(f"/api/flows/{resp.json()['id']}").status_code == 404

    def test_generate_retries_then_succeeds(self, client, monkeypatch):
        fake = _scripted(json.dumps(BROKEN_FLOW_JSON), json.dumps(VALID_FLOW_JSON))
        monkeypatch.setattr(llm_mod, "acomplete", fake)
        resp = client.post("/api/flows/generate", json={"prompt": "x"})
        assert resp.status_code == 201
        assert fake.calls["n"] == 2  # retried once

    def test_generate_all_invalid_returns_422(self, client, monkeypatch):
        monkeypatch.setattr(llm_mod, "acomplete", _scripted(json.dumps(BROKEN_FLOW_JSON)))
        resp = client.post("/api/flows/generate", json={"prompt": "x"})
        assert resp.status_code == 422
        assert "errors" in resp.json()["detail"]

    def test_generate_unparseable_returns_422(self, client, monkeypatch):
        monkeypatch.setattr(llm_mod, "acomplete", _scripted("not json at all"))
        resp = client.post("/api/flows/generate", json={"prompt": "x"})
        assert resp.status_code == 422

    def test_generate_handles_code_fences(self, client, monkeypatch):
        fenced = "```json\n" + json.dumps(VALID_FLOW_JSON) + "\n```"
        monkeypatch.setattr(llm_mod, "acomplete", _scripted(fenced))
        resp = client.post("/api/flows/generate", json={"prompt": "x"})
        assert resp.status_code == 201

    def test_generate_empty_prompt_422(self, client):
        resp = client.post("/api/flows/generate", json={"prompt": "   "})
        assert resp.status_code == 422

    def test_generate_without_llm_falls_back_offline(self, client, monkeypatch):
        async def boom(*a, **k):
            raise llm_mod.LLMUnavailable("no litellm")

        monkeypatch.setattr(llm_mod, "acomplete", boom)
        resp = client.post("/api/flows/generate", json={"prompt": "бот поддержки", "project_id": "p1"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["metadata"]["generated"] == "offline"
        assert data["project_id"] == "p1"
        assert data["node_count"] >= 2

    def test_generate_provider_error_falls_back_offline(self, client, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("401 invalid api key")

        monkeypatch.setattr(llm_mod, "acomplete", boom)
        resp = client.post("/api/flows/generate", json={"prompt": "x"})
        assert resp.status_code == 201
        assert resp.json()["metadata"]["generated"] == "offline"


class TestImproveFlow:
    def test_improve(self, client, monkeypatch):
        created = client.post(
            "/api/flows",
            json={
                "name": "f",
                "nodes": [{"id": "n1", "type": "end", "config": {}}],
                "start_node": "n1",
            },
        ).json()
        suggestion = {
            "suggestions": [
                {"node_id": "n1", "issue": "тупик", "recommendation": "добавь приветствие"}
            ],
            "summary": "ок",
        }
        monkeypatch.setattr(llm_mod, "acomplete", _scripted(json.dumps(suggestion)))
        resp = client.post(f"/api/flows/{created['id']}/improve", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["flow_id"] == created["id"]
        assert body["suggestions"][0]["node_id"] == "n1"
        assert body["summary"] == "ок"

    def test_improve_flow_not_found(self, client):
        resp = client.post("/api/flows/ghost/improve", json={})
        assert resp.status_code == 404
