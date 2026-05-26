from typing import Optional

from pydantic import BaseModel

from .message import InMessage, OutMessage


class Frame(BaseModel):
    '''
    Single activation frame on the execution call stack. The bottom of the
    stack is the main graph; pushed frames represent in-flight subgraph calls.
    Each frame has its own variable scope.
    '''
    subgraph_name: Optional[str] = None
    executing_node_id: str
    variable_values: dict[str, str | float] = {}

    # Return information (populated only for subgraph frames):
    exit_map: dict[str, str] = {}
    output_bindings: dict[str, str] = {}


class ExecutionState(BaseModel):
    '''
    Class representing the state of the execution that might be saved between
    calls to the engine.
    '''
    bot_id: int
    execution_id: int
    call_stack: list[Frame]

    @property
    def current_frame(self) -> Frame:
        return self.call_stack[-1]


class RunTimeExecutionState(ExecutionState):
    '''
    Class representing the execution state which only during the call to the
    engine.
    '''
    in_message: InMessage
    out_message: OutMessage
    send_message_flag: bool
