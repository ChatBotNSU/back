import logging

from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import SetVariable

from .FailExecutor import FailExecutor

logger = logging.getLogger("app")


def _as_number(v):
    if isinstance(v, bool):
        raise ValueError("bool is not a number")
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v))


class SetVariableExecutor():
    async def execute(self, execution_state: RunTimeExecutionState, node: SetVariable, chatbot: Chatbot):
        frame = execution_state.current_frame
        frame.executing_node_id = node.next_node_id

        name = node.assigned_variable
        op = node.operation
        operand = node.operand

        # Plain assignment creates the variable if missing; preserves operand's type.
        if op == "=":
            frame.variable_values[name] = operand
            return

        if name not in frame.variable_values:
            FailExecutor().execute(
                execution_state,
                f"Set variable executor: variable '{name}' is not defined; cannot apply '{op}'",
            )
            return

        current = frame.variable_values[name]

        if op == "+=":
            # Try numeric add; fall back to string concat (Python-ish).
            try:
                frame.variable_values[name] = _as_number(current) + _as_number(operand)
            except Exception:
                try:
                    frame.variable_values[name] = str(current) + str(operand)
                except Exception:
                    FailExecutor().execute(execution_state, f"Set variable executor: '+=' failed for '{name}'", "USER")
            return

        try:
            left = _as_number(current)
            right = _as_number(operand)
        except Exception:
            FailExecutor().execute(execution_state, f"Set variable executor: '{op}' requires numeric values for '{name}'", "USER")
            return

        if op == "-=":
            frame.variable_values[name] = left - right
        elif op == "*=":
            frame.variable_values[name] = left * right
        elif op == "/=":
            if right == 0:
                FailExecutor().execute(execution_state, f"Set variable executor: division by zero for '{name}'", "USER")
                return
            frame.variable_values[name] = left / right
        elif op == "%=":
            if right == 0:
                FailExecutor().execute(execution_state, f"Set variable executor: modulo by zero for '{name}'", "USER")
                return
            frame.variable_values[name] = left % right
        else:
            FailExecutor().execute(execution_state, f"Set variable executor: unknown operation '{op}'")
