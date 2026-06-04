from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class UserInputHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        pending = session.variables.pop("__pending_input__", None)

        if pending is None:
            # First pass: pause and wait for user reply
            session.variables["__waiting_node__"] = node.id
            if config.get("variable"):
                session.variables["__waiting_variable__"] = config["variable"]
            return {"__waiting__": True}

        # Second pass (after resume_flow): validate and store
        text = str(pending)
        input_type = config.get("input_type", "text")
        choices = config.get("choices", [])

        value: Any = text
        if input_type == "number":
            try:
                value = float(text)
            except ValueError:
                value = None
        elif choices and text not in choices:
            value = None

        variable = config.get("variable")
        if variable and value is not None:
            session.variables[variable] = value

        return {
            "text": text,
            "type": input_type,
            "value": value,
            "attachments": [],
            "__waiting__": False,
        }


register(NodeType.USER_INPUT, UserInputHandler())
