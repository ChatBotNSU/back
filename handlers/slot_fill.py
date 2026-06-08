from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class SlotFillHandler:
    """
    Collects multiple slots from the user one by one.
    Each call checks which slots are still missing and asks for the next one.
    Uses __pending_input__ for the resume-flow protocol.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        slots_config: list[dict[str, Any]] = config.get("slots", [])
        max_attempts: int = config.get("max_attempts", 3)

        # Load or initialise slot state stored in session
        slot_state_key = f"__slot_state_{node.id}__"
        slot_state: dict[str, Any] = session.variables.get(slot_state_key, {})

        # Process a pending answer if available
        pending = session.variables.pop("__pending_input__", None)
        waiting_slot = slot_state.get("__waiting_slot__")
        if pending is not None and waiting_slot:
            slot_state[waiting_slot] = pending
            slot_state.pop("__waiting_slot__", None)
            attempts = slot_state.get("__attempts__", {})
            attempts[waiting_slot] = 0
            slot_state["__attempts__"] = attempts

        session.variables[slot_state_key] = slot_state

        # Find the next missing slot
        for slot_def in slots_config:
            name = slot_def["name"]
            if name not in slot_state or slot_state[name] is None:
                attempts: dict[str, int] = slot_state.get("__attempts__", {})
                if attempts.get(name, 0) >= max_attempts:
                    # Too many retries — mark as failed
                    slot_state["__failed__"] = True
                    session.variables[slot_state_key] = slot_state
                    return self._build_output(slot_state, slots_config, complete=False)

                attempts[name] = attempts.get(name, 0) + 1
                slot_state["__attempts__"] = attempts
                slot_state["__waiting_slot__"] = name
                session.variables[slot_state_key] = slot_state

                # Store the prompt question so the caller can send it
                session.variables["__slot_question__"] = slot_def.get(
                    "question", f"Please provide {name}"
                )
                session.variables["__waiting_node__"] = node.id
                return {"__waiting__": True}

        # All slots collected
        return self._build_output(slot_state, slots_config, complete=True)

    @staticmethod
    def _build_output(
        slot_state: dict[str, Any],
        slots_config: list[dict[str, Any]],
        complete: bool,
    ) -> dict[str, Any]:
        slots = {s["name"]: slot_state.get(s["name"]) for s in slots_config}
        return {
            "slots": slots,
            "complete": complete,
            "attempts": slot_state.get("__attempts__", {}),
            "__waiting__": False,
        }


register(NodeType.SLOT_FILL, SlotFillHandler())
