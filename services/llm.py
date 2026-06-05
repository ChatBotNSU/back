from __future__ import annotations

from typing import Any

from config import settings


class LLMUnavailable(RuntimeError):
    """Raised when no LLM backend is installed/configured."""


_YANDEX_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


async def acomplete(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    response_format: dict[str, Any] | None = None,
) -> str:
    """
    Thin async wrapper around an LLM completion call.

    Routes to YandexGPT (Yandex Cloud) when configured, otherwise to litellm
    (OpenAI/etc). Isolated here so callers share one path and tests can
    monkeypatch `services.llm.acomplete`. Returns the assistant text.
    Raises LLMUnavailable when no backend is available.
    """
    if settings.llm_provider == "yandex" or model.startswith("yandexgpt"):
        return await _yandex_complete(model, messages, temperature)
    return await _litellm_complete(model, messages, temperature, response_format)


async def _litellm_complete(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    response_format: dict[str, Any] | None,
) -> str:
    try:
        import litellm  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch in tests
        raise LLMUnavailable("litellm is not installed") from exc

    kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if response_format is not None:
        kwargs["response_format"] = response_format

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content or ""


async def _yandex_complete(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
) -> str:
    """Call YandexGPT (Foundation Models). Needs YANDEX_API_KEY + YANDEX_FOLDER_ID."""
    api_key = settings.yandex_api_key
    folder_id = settings.yandex_folder_id
    if not api_key or not folder_id:
        raise LLMUnavailable("YANDEX_API_KEY / YANDEX_FOLDER_ID are not set")

    import httpx

    # Allow either a short name ("yandexgpt-lite") or a full gpt:// URI.
    model_uri = model if model.startswith("gpt://") else f"gpt://{folder_id}/{model}/latest"

    body = {
        "modelUri": model_uri,
        "completionOptions": {"temperature": temperature, "maxTokens": 2000},
        "messages": [
            {"role": m.get("role", "user"), "text": str(m.get("content", ""))}
            for m in messages
        ],
    }
    headers = {"Authorization": f"Api-Key {api_key}", "x-folder-id": folder_id}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_YANDEX_URL, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    alternatives = data.get("result", {}).get("alternatives", [])
    if not alternatives:
        return ""
    return alternatives[0].get("message", {}).get("text", "")
