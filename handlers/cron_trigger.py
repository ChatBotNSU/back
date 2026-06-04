from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class CronTriggerHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        return {
            "fired_at": session.variables.get(
                "fired_at",
                datetime.now(timezone.utc).isoformat(),
            ),
            "recipients": session.variables.get("recipients", []),
        }


register(NodeType.CRON_TRIGGER, CronTriggerHandler())
