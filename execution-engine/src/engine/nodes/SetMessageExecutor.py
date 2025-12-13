from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import SetMessage

from .FailExecutor import FailExecutor


class SetMessageExecutor():
    async def execute(self, execution: RunTimeExecutionState, node: SetMessage, chatbot: Chatbot):
        execution.out_message.text = node.text.format(**execution.variable_values)
        execution.out_message.audios = node.audios
        execution.out_message.images = node.images
        execution.out_message.files = node.files
        execution.out_message.choise_options = node.choise_options
        execution.executing_node_id = node.next_node_id
