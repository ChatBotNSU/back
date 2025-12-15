import asyncio
import uuid

from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import ScriptExecution

from .FailExecutor import FailExecutor
from sandbox_runner.client import PyRunnerClient

class ScriptNodeExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: ScriptExecution, chatbot: Chatbot):
        code = getattr(node, "code", None) or getattr(node, "script", None)
        if not code or not isinstance(code, str):
            FailExecutor().execute(execution_state, "Script executor: node has no 'code' (or 'script') field")
            return

        schema: dict[str, str] = {}
        variables: dict[str, str | int] = {}

        declared_types = {v.name: v.type for v in getattr(chatbot, "variables", [])}

        for name, declared_type in declared_types.items():
            if declared_type == "number":
                schema[name] = "int"
            else:
                schema[name] = "str"

            val = execution_state.variable_values.get(name)

            if schema[name] == "int":
                try:
                    if isinstance(val, bool):
                        raise ValueError("bool is not allowed for int")
                    if isinstance(val, int):
                        variables[name] = val
                    elif isinstance(val, float):
                        variables[name] = int(val)
                    elif val is None:
                        variables[name] = 0
                    else:
                        variables[name] = int(str(val))
                except Exception:
                    FailExecutor().execute(execution_state, f"Script executor: variable '{name}' must be int-compatible")
                    return
            else:
                try:
                    variables[name] = "" if val is None else str(val)
                except Exception:
                    FailExecutor().execute(execution_state, f"Script executor: variable '{name}' must be str-compatible")
                    return

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

        if resp.variables:
            execution_state.variable_values.update(resp.variables)
        if resp.added_variables:
            execution_state.variable_values.update(resp.added_variables)

        execution_state.executing_node_id = node.next_node_id
