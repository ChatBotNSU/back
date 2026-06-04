from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class EndHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        if config.get("reset_session"):
            session.variables.clear()
            session.node_outputs.clear()

        message = config.get("message", "")
        if message:
            session.variables.setdefault("__messages__", []).append(
                {"content_type": "text", "text": message}
            )

        return {}


register(NodeType.END, EndHandler())
