import asyncio
import uuid

from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import ScriptExecution

from .FailExecutor import FailExecutor
from sandbox_runner.client import PyRunnerClient


def _infer_type(value) -> str:
    if isinstance(value, bool):
        return "str"
    if isinstance(value, (int, float)):
        return "int"
    return "str"


class ScriptNodeExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: ScriptExecution, chatbot: Chatbot):
        frame = execution_state.current_frame

        code = getattr(node, "code", None) or getattr(node, "script", None)
        if not code or not isinstance(code, str):
            FailExecutor().execute(execution_state, "Script executor: node has no 'code' (or 'script') field")
            return

        # Dynamic types: infer schema from current runtime values in this scope.
        schema: dict[str, str] = {}
        variables: dict[str, int | str] = {}
        for name, val in frame.variable_values.items():
            inferred = _infer_type(val)
            schema[name] = inferred
            if inferred == "int":
                try:
                    variables[name] = int(val) if not isinstance(val, bool) else 0
                except Exception:
                    variables[name] = 0
            else:
                variables[name] = "" if val is None else str(val)

        client = PyRunnerClient()
        job_id = f"{uuid.uuid4()}"

        def _call_runner():
            return client.run(
                code=code,
                variables=variables,
                schema=schema,
                job_id=job_id,
                timeout_seconds=getattr(node, "timeout_seconds", 8),
                memory_mb=getattr(node, "memory_mb", 256),
            )

        try:
            resp = await asyncio.to_thread(_call_runner)
        except Exception as e:
            FailExecutor().execute(execution_state, f"Script executor: runner call failed: {e}")
            return

        if resp.status != "OK":
            err = (resp.error.message if resp.error else resp.status)
            FailExecutor().execute(execution_state, f"Script executor: {err}")
            return

        # Any variable returned by the runner becomes available in the current scope.
        if resp.variables:
            for k, v in resp.variables.items():
                frame.variable_values[k] = v

        if getattr(resp, "removed_variables", None):
            for k in resp.removed_variables:
                frame.variable_values.pop(k, None)

        frame.executing_node_id = node.next_node_id
