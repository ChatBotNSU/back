import asyncio

from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import Wait


class WaitExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: Wait, chatbot: Chatbot):
        await asyncio.sleep(node.wait_time)
        execution_state.current_frame.executing_node_id = node.next_node_id
