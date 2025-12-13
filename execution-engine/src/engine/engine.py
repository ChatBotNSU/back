import asyncio
import logging

from models.chatbot import Chatbot
from models.execution_state import ExecutionState, RunTimeExecutionState, InMessage, OutMessage
from .nodes import FailExecutor, SendMessageExecutor, SetMessageExecutor, SetVariableExecutor, TextAnswerExecutor


logger = logging.getLogger("app")

node_executors = {
    "text_answer": TextAnswerExecutor(),
    "set_message": SetMessageExecutor(),
    "set_variable": SetVariableExecutor(),
    "send_message": SendMessageExecutor(),
}

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

            logger.info(f"Executing node: {self.execution_state}")
            logger.info(f"Runtime execution state: {self.runtime_execution_state}")

            self.runtime_execution_state.out_message.text = "IDI NAHUY"

            while not self.runtime_execution_state.send_message_flag:
                logger.info(f"DO I WANNA KILL MYSELF??? OF COURSE {self.runtime_execution_state.executing_node_id}")
                next_node = self.chatbot.graph.nodes[self.runtime_execution_state.executing_node_id]
                logger.info(f"DO I WANNA KILL MYSELF??? OF COURSE {self.runtime_execution_state.executing_node_id} {self.chatbot.graph.nodes}")

                if next_node.type not in node_executors:
                    FailExecutor().execute(self.runtime_execution_state, f"Node executor not found: {next_node.type}")
                    return self.runtime_execution_state.out_message

                logger.info(f"Executing node: {next_node}")
                await node_executors[next_node.type].execute(self.runtime_execution_state, next_node, self.chatbot)
                logger.info(f"DO I WANNA KILL MYSELF??? OF COURSE {self.runtime_execution_state.executing_node_id}")
                if self.runtime_execution_state.send_message_flag:
                    break

            logger.info("Sending message")
            self.execution_state = ExecutionState.model_validate(self.runtime_execution_state.model_dump())
            return self.runtime_execution_state.out_message
            