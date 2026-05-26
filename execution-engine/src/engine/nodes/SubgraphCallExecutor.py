from models.execution_state import RunTimeExecutionState, Frame
from models.chatbot import Chatbot
from models.nodes import SubgraphCall

from .FailExecutor import FailExecutor


class SubgraphCallExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: SubgraphCall, chatbot: Chatbot):
        caller_frame = execution_state.current_frame

        subgraph = chatbot.subgraphs.get(node.subgraph_name)
        if subgraph is None:
            FailExecutor().execute(execution_state, f"Subgraph call: unknown subgraph '{node.subgraph_name}'")
            return

        # Every declared input must be bound by the caller.
        declared_inputs = set(subgraph.inputs)
        provided = set(node.input_bindings.keys())
        missing_inputs = declared_inputs - provided
        if missing_inputs:
            FailExecutor().execute(
                execution_state,
                f"Subgraph call: missing bindings for inputs {sorted(missing_inputs)} of '{node.subgraph_name}'",
            )
            return
        unknown_inputs = provided - declared_inputs
        if unknown_inputs:
            FailExecutor().execute(
                execution_state,
                f"Subgraph call: '{sorted(unknown_inputs)}' are not declared inputs of '{node.subgraph_name}'",
            )
            return

        # Caller-side variables referenced by bindings must exist (by-ref semantics).
        for sub_input, caller_var in node.input_bindings.items():
            if caller_var not in caller_frame.variable_values:
                FailExecutor().execute(
                    execution_state,
                    f"Subgraph call: caller variable '{caller_var}' is not defined",
                )
                return

        # exit_next_nodes must cover every declared exit.
        missing_exits = [e for e in subgraph.exits if e not in node.exit_next_nodes]
        if missing_exits:
            FailExecutor().execute(
                execution_state,
                f"Subgraph call: exit_next_nodes missing labels {missing_exits} for subgraph '{node.subgraph_name}'",
            )
            return

        # Fresh local scope seeded from the input bindings only (by-ref view of caller vars).
        locals_: dict[str, str | float] = {
            sub_input: caller_frame.variable_values[caller_var]
            for sub_input, caller_var in node.input_bindings.items()
        }

        new_frame = Frame(
            subgraph_name=node.subgraph_name,
            executing_node_id=subgraph.graph.root,
            variable_values=locals_,
            exit_map=dict(node.exit_next_nodes),
            # Write-back map for return: same shape as input_bindings (sub_local -> caller_var).
            output_bindings=dict(node.input_bindings),
        )
        execution_state.call_stack.append(new_frame)
