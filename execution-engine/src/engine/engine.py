import asyncio

from src.models.chatbot import Chatbot
from src.models.execution_state import ExecutionState, RunTimeExecutionState, InMessage

class Engine:
    chatbot: Chatbot
    execution_state: ExecutionState
    runtime_execution_state: RunTimeExecutionState
    _lock: asyncio.Lock

    def __init__(self, chatbot: Chatbot, execution_state: ExecutionState):
        self._lock = asyncio.Lock()
        self.chatbot = chatbot
        self.execution_state = execution_state

    async def execute(self, message: InMessage):
        async with self._lock:
            self.runtime_execution_state = RunTimeExecutionState(**execution_state.model_dump())

            next_node = self.chatbot.graph.nodes[self.execution_state.executing_node_id]

