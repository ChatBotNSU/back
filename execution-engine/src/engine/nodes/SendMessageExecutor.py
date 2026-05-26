from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import SendMessage

class SendMessageExecutor():
    async def execute(self, execution_state: RunTimeExecutionState, node: SendMessage, chatbot: Chatbot):
        execution_state.send_message_flag = True
        execution_state.current_frame.executing_node_id = node.next_node_id
