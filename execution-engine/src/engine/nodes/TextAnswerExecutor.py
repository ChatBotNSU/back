from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import TextAnswer
from .FailExecutor import FailExecutor


class TextAnswerExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: TextAnswer, chatbot: Chatbot):
        if execution_state.in_message.text is None:
            FailExecutor().execute(execution_state, "Text answer executor: in message has no text")
            return

        frame = execution_state.current_frame
        frame.variable_values[node.assigned_variable] = execution_state.in_message.text
        frame.executing_node_id = node.next_node_id
