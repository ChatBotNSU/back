"""Tests for the YandexGPT provider path in services.llm (mocked httpx)."""
from __future__ import annotations

import httpx
import pytest

import services.llm as llm
from config import settings


@pytest.fixture()
def yandex_env(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "yandex")
    monkeypatch.setattr(settings, "yandex_api_key", "test-key")
    monkeypatch.setattr(settings, "yandex_folder_id", "fold-1")


def _patch_httpx(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler),
                          **{k: v for k, v in kw.items() if k != "transport"}),
    )


class TestYandexProvider:
    async def test_builds_uri_and_parses_text(self, yandex_env, monkeypatch):
        seen = {}

        def handler(req):
            import json
            seen["body"] = json.loads(req.content)
            seen["auth"] = req.headers.get("authorization")
            return httpx.Response(200, json={
                "result": {"alternatives": [{"message": {"role": "assistant", "text": "ответ"}}]}
            })

        _patch_httpx(monkeypatch, handler)
        out = await llm.acomplete("yandexgpt-lite", [{"role": "user", "content": "привет"}], temperature=0.3)

        assert out == "ответ"
        assert seen["auth"] == "Api-Key test-key"
        assert seen["body"]["modelUri"] == "gpt://fold-1/yandexgpt-lite/latest"
        assert seen["body"]["messages"] == [{"role": "user", "text": "привет"}]

    async def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "yandex")
        monkeypatch.setattr(settings, "yandex_api_key", "")
        monkeypatch.setattr(settings, "yandex_folder_id", "")
        with pytest.raises(llm.LLMUnavailable):
            await llm.acomplete("yandexgpt-lite", [{"role": "user", "content": "x"}])
