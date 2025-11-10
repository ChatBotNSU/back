from pydantic import BaseModel


class ExecutionState(BaseModel):
    '''
    Class representing the state of the execution that might be saved between calls to the engine.
    '''
    bot_id: int # id of the bot for execution
    chat_id: int # if of the chat being executed
    executing_node_id: int # if of the node being executed
    variable_values: dict[str, str|int]



class Message(BaseModel):
    text: str | None # text of the message
    images: list[str] | None # paths to the images
    audios: list[str] | None # paths to the audios
    files: list[str] | None # paths to the files

class InMessage(Message):
    restart_command: bool # flag showing if the message is a restart command

class OutMessage(Message):
    choise_options: list[str] | None # if set then choise options (buttons with messages to send) should be set for user in telegram. 



class RunTimeExecutionState(ExecutionState):
    '''
    Class representing the execution state which only during the call to the engine
    '''
    in_message: InMessage
    out_message: OutMessage
    send_message_flag: bool # flag showing if a message should be sent right now
