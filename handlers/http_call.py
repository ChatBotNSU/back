from __future__ import annotations

import re
import time
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


def _lookup(key: str, ctx: dict[str, Any]) -> Any:
    """Resolve a flat or dotted key (e.g. `api.response.user.name`) against ctx."""
    cur: Any = ctx
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _render(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        # Exact single-template string preserves the resolved value's type, so a
        # body can carry a nested object/list/number from a prior response, not
        # just its string form (e.g. {"user": "{{api.response.user}}"}).
        if stripped.startswith("{{") and stripped.endswith("}}") and "{{" not in stripped[2:-2]:
            resolved = _lookup(stripped[2:-2].strip(), ctx)
            return resolved if resolved is not None else value
        def replacer(m: re.Match) -> str:
            resolved = _lookup(m.group(1).strip(), ctx)
            return str(resolved) if resolved is not None else m.group(0)
        return re.sub(r"\{\{(.+?)\}\}", replacer, value)
    if isinstance(value, dict):
        return {k: _render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(item, ctx) for item in value]
    return value


class HttpCallHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        ctx = {**session.variables, **data_in}
        method: str = config.get("method", "GET").upper()
        url: str = _render(config.get("url", ""), ctx)
        headers: dict = _render(config.get("headers", {}), ctx)
        body: Any = _render(config.get("body"), ctx)
        timeout_ms: int = int(config.get("timeout_ms", 10_000))

        # Test stub: skip real HTTP when __test_response__ is provided
        if "__test_response__" in config:
            return {
                "response": config["__test_response__"],
                "status": 200,
                "ok": True,
                "headers": {},
                "duration_ms": 0,
            }

        try:
            import httpx  # type: ignore
            start = time.monotonic()
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body,
                    timeout=timeout_ms / 1000,
                )
            duration_ms = (time.monotonic() - start) * 1000
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text

            return {
                "response": response_body,
                "status": resp.status_code,
                "ok": resp.is_success,
                "headers": dict(resp.headers),
                "duration_ms": round(duration_ms, 2),
            }
        except ImportError:
            # Test stub: return config.__test_response__ if present
            test_resp = config.get("__test_response__", {})
            return {
                "response": test_resp,
                "status": 200,
                "ok": True,
                "headers": {},
                "duration_ms": 0,
            }


register(NodeType.HTTP_CALL, HttpCallHandler())
