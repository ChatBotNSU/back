from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class WebhookTriggerHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        return {
            "payload": session.variables.get("payload", {}),
            "headers": session.variables.get("headers", {}),
            "method": session.variables.get("method", "POST"),
            "triggered_at": session.variables.get("triggered_at", ""),
        }


register(NodeType.WEBHOOK_TRIGGER, WebhookTriggerHandler())
