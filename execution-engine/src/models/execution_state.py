from pydantic import BaseModel

from .message import InMessage, OutMessage


class ExecutionState(BaseModel):
    '''
    Class representing the state of the execution that might be saved between calls to the engine.
    '''
    bot_id: int # id of the bot for execution
    execution_id: str # id of the execution
    executing_node_id: int # id of the node being executed
    variable_values: dict[str, str|int]


class RunTimeExecutionState(ExecutionState):
    '''
    Class representing the execution state which only during the call to the engine
    '''
    in_message: InMessage
    out_message: OutMessage
    send_message_flag: bool # flag showing if a message should be sent right now
