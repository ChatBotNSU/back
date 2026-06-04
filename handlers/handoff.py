from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class HandoffHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        # Check if operator resolved the session
        resolved = session.variables.pop("__handoff_resolved__", None)
        if resolved is not None:
            return {
                "operator_id": session.variables.get("__operator_id__", ""),
                "resolved": True,
                "duration_sec": session.variables.get("__handoff_duration__", 0),
                "__waiting__": False,
            }

        # First entry: notify operator and pause
        forward_to: str = config.get("forward_to", "")
        notify_msg: str = config.get("notify_msg", "New conversation assigned")
        session.variables["__waiting_node__"] = node.id
        session.variables["__handoff_target__"] = forward_to
        session.variables["__handoff_notify__"] = notify_msg

        return {
            "operator_id": "",
            "resolved": False,
            "duration_sec": 0,
            "__waiting__": True,
        }


register(NodeType.HANDOFF, HandoffHandler())
