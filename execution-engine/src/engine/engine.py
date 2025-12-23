import asyncio
import logging

from models.chatbot import Chatbot
from models.execution_state import ExecutionState, RunTimeExecutionState, InMessage, OutMessage
from .nodes import (
    FailExecutor,
    SendMessageExecutor,
    SetMessageExecutor,
    SetVariableExecutor,
    TextAnswerExecutor,
    ScriptNodeExecutor,
    WaitExecutor,
    FileAnswerExecutor
)

logger = logging.getLogger("app")

node_executors = {
    "text_answer": TextAnswerExecutor(),
    "set_message": SetMessageExecutor(),
    "set_variable": SetVariableExecutor(),
    "send_message": SendMessageExecutor(),
    "script_execution": ScriptNodeExecutor(),
    "condition": ConditionNodeExecutor(),
    "wait": WaitExecutor(),
    "file_answer": FileAnswerExecutor()
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
            while not self.runtime_execution_state.send_message_flag:
                next_node = self.chatbot.graph.nodes[self.runtime_execution_state.executing_node_id]
                logger.info(f"Executing node: {next_node}")
                if next_node.type not in node_executors:
                    FailExecutor().execute(self.runtime_execution_state, f"Node executor not found: {next_node.type}")
                    return self.runtime_execution_state.out_message

                await node_executors[next_node.type].execute(self.runtime_execution_state, next_node, self.chatbot)
                if self.runtime_execution_state.send_message_flag:
                    break

            logger.info("Sending message")
            self.execution_state = ExecutionState.model_validate(self.runtime_execution_state.model_dump())
            return self.runtime_execution_state.out_message
            
