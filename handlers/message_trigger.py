from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class MessageTriggerHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        # Trigger data is pre-loaded into session.variables on webhook receipt.
        # Here we just expose it as data_out so downstream nodes can use data ports.
        return {
            "user_id": session.variables.get("user_id", ""),
            "session_id": session.id,
            "text": session.variables.get("text", ""),
            "channel": session.channel or session.variables.get("channel", ""),
            "attachments": session.variables.get("attachments", []),
            "user_meta": session.variables.get("user_meta", {}),
        }


register(NodeType.MESSAGE_TRIGGER, MessageTriggerHandler())
