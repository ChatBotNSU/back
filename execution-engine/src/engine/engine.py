import asyncio
import logging

from models.chatbot import Chatbot
from models.execution_state import ExecutionState, RunTimeExecutionState, InMessage, OutMessage

logger = logging.getLogger("app")

class Engine:

    chatbot: Chatbot
    execution_state: ExecutionState
    runtime_execution_state: RunTimeExecutionState
    _lock: asyncio.Lock

    def __init__(self, chatbot: Chatbot, execution_state: ExecutionState):
        self._lock = asyncio.Lock()
        self.chatbot = chatbot
        self.execution_state = execution_state

    async def execute(self, message: InMessage) -> OutMessage:
        async with self._lock:
            self.runtime_execution_state = RunTimeExecutionState(**self.execution_state.model_dump(),
                                                                send_message_flag=False,
                                                                in_message=message,
                                                                out_message=OutMessage())

            self.runtime_execution_state.out_message.text = "IDI NAHUY"

            while not self.runtime_execution_state.send_message_flag:
                next_node = self.chatbot.graph.nodes[self.execution_state.executing_node_id]
                logger.info(f"Executing node: {next_node}")
                self.runtime_execution_state.send_message_flag = True

            logger.info("Sending message")
            return self.runtime_execution_state.out_message
            

