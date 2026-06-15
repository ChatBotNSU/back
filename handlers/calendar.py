from __future__ import annotations

import logging
from typing import Any

from engine.registry import register
from integrations.calendar import CalendarError, build_provider
from models.node import Node, NodeType
from models.session import Session
from services import connections

logger = logging.getLogger(__name__)


def _render(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return ctx.get(value[2:-2].strip())
    return value


class CalendarHandler:
    """Google Calendar / Calendly with stub fallback when no provider/creds set."""

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        config = await connections.resolve(config, session)
        provider: str = config.get("provider", "")
        action: str = config.get("action", "create")
        ctx = {**session.variables, **data_in}

        if not provider and "token" not in config:
            return self._stub(action, config)

        params = {
            "title": _render(config.get("title", ""), ctx),
            "start": _render(config.get("start"), ctx),
            "end": _render(config.get("end"), ctx),
            "attendee_email": _render(config.get("attendee_email"), ctx),
            "event_id": _render(config.get("event_id"), ctx),
            "time_min": config.get("time_min"),
            "time_max": config.get("time_max"),
            "user": config.get("user"),
        }

        client = config.get("__client__")
        try:
            impl = build_provider(provider, config, client=client)
        except CalendarError as exc:
            return {"provider": provider, "action": action, "ok": False, "error": str(exc)}

        if impl is None:
            return self._stub(action, config)

        try:
            return await impl.execute(action, params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Calendar %s failed: %s", action, exc)
            return {"provider": provider, "action": action, "ok": False, "error": str(exc)}

    @staticmethod
    def _stub(action: str, config: dict[str, Any]) -> dict[str, Any]:
        if action == "slots":
            return {"event": None, "slots": ["09:00", "10:00", "11:00"], "cancelled": False, "stub": True}
        if action == "cancel":
            return {"event": None, "slots": [], "cancelled": True, "stub": True}
        return {
            "event": {"title": config.get("title", ""), "provider": config.get("provider", "google")},
            "slots": [], "cancelled": False, "stub": True,
        }


register(NodeType.CALENDAR, CalendarHandler())
