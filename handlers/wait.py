from __future__ import annotations

import asyncio
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class WaitHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        wait_type: str = config.get("type", "delay")

        if wait_type == "delay":
            delay_ms: int = int(config.get("delay_ms", 1000))
            await asyncio.sleep(delay_ms / 1000)
            return {
                "elapsed_ms": delay_ms,
                "event_payload": {},
                "timed_out": False,
                "__waiting__": False,
            }

        if wait_type in ("webhook", "condition"):
            # Check if we already received the event
            event_payload = session.variables.pop(f"__wait_event_{node.id}__", None)
            if event_payload is not None:
                return {
                    "elapsed_ms": 0,
                    "event_payload": event_payload,
                    "timed_out": False,
                    "__waiting__": False,
                }
            # Pause and wait
            session.variables["__waiting_node__"] = node.id
            session.variables["__wait_key__"] = config.get("webhook_key", node.id)
            return {"__waiting__": True}

        return {"elapsed_ms": 0, "event_payload": {}, "timed_out": False, "__waiting__": False}


register(NodeType.WAIT, WaitHandler())
