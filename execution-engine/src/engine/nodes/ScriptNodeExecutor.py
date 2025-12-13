import asyncio

from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import ScriptExecution


class ScriptNodeExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: ScriptExecution, chatbot: Chatbot):
        # TODO: make execution which updates execution_state.variable_values
        
        execution_state.executing_node_id = node.next_node_id
