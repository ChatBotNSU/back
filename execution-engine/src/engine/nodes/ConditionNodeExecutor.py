from models.execution_state import RunTimeExecutionState
from models.nodes import ConditionNode
from models.chatbot import Chatbot

from .FailExecutor import FailExecutor

class ConditionNodeExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: ConditionNode, chatbot: Chatbot):
        frame = execution_state.current_frame
        for branch in node.branches:
            condition = branch.condition

            try:
                left_variable = frame.variable_values[condition.variable_left]
                right_variable = frame.variable_values[condition.variable_right]
            except:
                FailExecutor().execute(execution_state, "Condition executor: variable not found")
                return

            if condition.operation == "==":
                if left_variable == right_variable:
                    frame.executing_node_id = branch.next_node_id
                    return
            elif condition.operation == "!=":
                if left_variable != right_variable:
                    frame.executing_node_id = branch.next_node_id
                    return

            try:
                left_variable = float(left_variable)
                right_variable = float(right_variable)
            except:
                FailExecutor().execute(execution_state, "Condition executor: variable type mismatch")
                return

            if condition.operation == "<":
                if left_variable < right_variable:
                    frame.executing_node_id = branch.next_node_id
                    return
            elif condition.operation == ">":
                if left_variable > right_variable:
                    frame.executing_node_id = branch.next_node_id
                    return
            elif condition.operation == "<=":
                if left_variable <= right_variable:
                    frame.executing_node_id = branch.next_node_id
                    return
            elif condition.operation == ">=":
                if left_variable >= right_variable:
                    frame.executing_node_id = branch.next_node_id
                    return

        frame.executing_node_id = node.default_next_node_id
