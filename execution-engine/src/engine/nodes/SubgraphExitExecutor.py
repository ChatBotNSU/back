from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import SubgraphExit

from .FailExecutor import FailExecutor


class SubgraphExitExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: SubgraphExit, chatbot: Chatbot):
        if len(execution_state.call_stack) < 2:
            FailExecutor().execute(execution_state, "Subgraph exit: no caller frame to return to")
            return

        exiting = execution_state.call_stack.pop()

        if node.exit_label not in exiting.exit_map:
            FailExecutor().execute(
                execution_state,
                f"Subgraph exit: caller did not register label '{node.exit_label}'",
            )
            return

        caller = execution_state.current_frame

        for sub_out, caller_var in exiting.output_bindings.items():
            if sub_out in exiting.variable_values:
                caller.variable_values[caller_var] = exiting.variable_values[sub_out]

        caller.executing_node_id = exiting.exit_map[node.exit_label]
