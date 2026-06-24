from __future__ import annotations

import logging
import re
from typing import Any

from engine.registry import register
from integrations.sheets import SheetsError, build_provider
from models.node import Node, NodeType
from models.session import Session
from services import connections

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
        provider: str = config.get("provider", "")
        action: str = config.get("action", "read")

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
        try:
            return await impl.execute(
                action,
                _render(config.get("range", "A1"), ctx),
                _render(config.get("values", []), ctx),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sheets %s failed: %s", action, exc)
            return {"provider": provider, "action": action, "ok": False, "error": str(exc)}

    @staticmethod
    def _stub(action: str, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": config.get("provider", ""), "action": action, "ok": True,
            "rows": [], "stub": True,
        }


register(NodeType.SHEETS, SheetsHandler())
