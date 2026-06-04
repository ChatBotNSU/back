from __future__ import annotations

import re
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


def _render(template: str, ctx: dict[str, Any]) -> str:
    def replacer(m: re.Match) -> str:
        key = m.group(1).strip()
        return str(ctx.get(key, m.group(0)))
    return re.sub(r"\{\{(.+?)\}\}", replacer, template)


class NotifyHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        ctx = {**session.variables, **data_in}
        channel: str = config.get("channel", "telegram")
        to: str = _render(str(config.get("to", "")), ctx)
        message: str = _render(config.get("message", ""), ctx)

        # Real implementation would dispatch to the channel adapter.
        return {
            "sent": True,
            "message_id": f"stub-{channel}-001",
            "channel": channel,
            "to": to,
            "message": message,
        }


register(NodeType.NOTIFY, NotifyHandler())
