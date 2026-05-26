from models.execution_state import RunTimeExecutionState
from models.nodes import FileAnswer
from models.chatbot import Chatbot

from .FailExecutor import FailExecutor


class FileAnswerExecutor():
    async def execute(self, execution_state: RunTimeExecutionState, node: FileAnswer, chatbot: Chatbot):
        frame = execution_state.current_frame
        in_msg = execution_state.in_message

        if in_msg.files:
            frame.variable_values[node.assigned_variable] = in_msg.files[0]
        elif in_msg.audios:
            frame.variable_values[node.assigned_variable] = in_msg.audios[0]
        elif in_msg.images:
            frame.variable_values[node.assigned_variable] = in_msg.images[0]
        else:
            FailExecutor().execute(execution_state, "File answer executor: in message doesn't contain any file path")
            return

        frame.executing_node_id = node.next_node_id
