from __future__ import annotations

import json
import logging
import re
from typing import Any

from engine.registry import register
from integrations.sheets import SheetsError, build_provider
from models.node import Node, NodeType
from models.session import Session
from services import connections
from services.google_auth import GoogleAuthError, get_access_token, looks_like_service_account

logger = logging.getLogger(__name__)


def _render(value: Any, ctx: dict[str, Any]) -> Any:
    """Recursively substitute {{var}} placeholders from session variables."""
    if isinstance(value, str):
        return re.sub(r"\{\{(.+?)\}\}", lambda m: str(ctx.get(m.group(1).strip(), m.group(0))), value)
    if isinstance(value, list):
        return [_render(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _render(v, ctx) for k, v in value.items()}
    return value


def _parse_values(raw: Any) -> list[list[Any]]:
    """Normalize the user-provided `values` config into Sheets' list-of-lists.

    Accepts: already-structured 2D list, a 1D list (single row), a JSON string,
    or a CSV-ish multiline string ("a,b\nc,d"). Empty/missing → [].
    """
    if raw in (None, "", []):
        return []
    if isinstance(raw, list):
        if raw and not isinstance(raw[0], list):
            return [raw]
        return raw  # already 2D
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                parsed = json.loads(s)
                return _parse_values(parsed)
            except json.JSONDecodeError:
                pass
        # CSV-ish fallback: split by newlines, then commas.
        rows = [
            [cell.strip() for cell in line.split(",")]
            for line in s.splitlines()
            if line.strip()
        ]
        return rows
    return []


async def _ensure_access_token(config: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """If the bundle carries a service-account JSON, mint a fresh access token
    and put it under config['token']. Returns (new_config, mint_error).
    `mint_error` is None on success, an explanatory string on failure (so it
    can be surfaced to the Demo UI), or None when there's no SA to mint from.
    """
    sa = config.get("service_account_json")
    if not isinstance(sa, dict):
        # Maybe the bundle IS the SA JSON directly (no wrapper key).
        if looks_like_service_account(config):
            sa = {
                k: config[k]
                for k in ("type", "client_email", "private_key", "private_key_id")
                if k in config
            }
        else:
            sa = None
    if sa is None:
        return config, None
    try:
        token = await get_access_token(sa)
    except GoogleAuthError as exc:
        msg = f"google sheets: SA token mint failed — {exc}"
        logger.warning(msg)
        return config, msg
    except Exception as exc:  # noqa: BLE001
        msg = f"google sheets: unexpected token mint error — {exc!r}"
        logger.exception(msg)
        return config, msg
    return {**config, "token": token}, None


class SheetsHandler:
    """Google Sheets integration with stub fallback when no provider/creds set."""

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        config = await connections.resolve(config, session)
        config, mint_error = await _ensure_access_token(config)
        provider: str = config.get("provider", "") or "google"
        action: str = config.get("action", "read")

        if mint_error:
            # Surface the *actual* reason instead of letting the provider die
            # with the generic "token and spreadsheet_id are required".
            return {"provider": provider, "action": action, "ok": False, "error": mint_error}

        if not provider and "spreadsheet_id" not in config:
            return self._stub(action, config)

        client = config.get("__client__")
        try:
            impl = build_provider(provider, config, client=client)
        except SheetsError as exc:
            return {"provider": provider, "action": action, "ok": False, "error": str(exc)}

        if impl is None:
            return self._stub(action, config)

        ctx = {**session.variables, **data_in}
        rendered_range = _render(config.get("range", "A1"), ctx)
        rendered_values = _parse_values(_render(config.get("values", []), ctx))
        try:
            result = await impl.execute(action, rendered_range, rendered_values)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sheets %s failed: %s", action, exc)
            return {"provider": provider, "action": action, "ok": False, "error": str(exc)}

        # Convenience for downstream {{var}} when reading.
        output_var = config.get("output_var")
        if output_var and action == "read":
            session.variables[output_var] = result.get("rows", [])
        return result

    @staticmethod
    def _stub(action: str, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": config.get("provider", ""), "action": action, "ok": True,
            "rows": [], "stub": True,
        }


register(NodeType.SHEETS, SheetsHandler())
