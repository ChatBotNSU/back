from __future__ import annotations

import re
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


def _render(template: Any, variables: dict[str, Any]) -> Any:
    if not isinstance(template, str):
        return template
    def replacer(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))
    return re.sub(r"\{\{(.+?)\}\}", replacer, template)


class SendMessageHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        vars_ctx = {**session.variables, **data_in}
        content_type = config.get("content_type", "text")
        text = _render(config.get("text", ""), vars_ctx)

        message: dict[str, Any] = {"content_type": content_type, "text": text}

        if content_type in ("image", "video"):
            message["media_url"] = _render(config.get("media_url", ""), vars_ctx)
        if content_type == "buttons":
            message["buttons"] = config.get("buttons", [])
        if content_type == "carousel":
            message["cards"] = config.get("cards", [])

        # Typing delay stub (real impl would use asyncio.sleep + channel API)
        # typing_delay = config.get("typing_delay", 0)

        session.variables.setdefault("__messages__", []).append(message)

        # Attempt real delivery via channel adapter
        channel = session.variables.get("channel", "")
        recipient = str(
            session.variables.get("chat_id")
            or session.variables.get("user_id")
            or ""
        )
        bot_token = session.variables.get("__bot_token__", "")

        message_id = ""
        delivered = False

        if channel and recipient and bot_token:
            try:
                from adapters import registry as adapter_registry
                result = await adapter_registry.send(channel, bot_token, recipient, message)
                message_id = result.get("message_id", "")
                delivered = result.get("ok", False)
            except Exception:
                pass  # delivery failure is non-fatal for the flow

        return {
            "message_id": message_id,
            "delivered": delivered,
            "message": message,
        }


register(NodeType.SEND_MESSAGE, SendMessageHandler())
