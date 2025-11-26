from pydantic import BaseModel

from .message import InMessage, OutMessage

class ExecutionRequest(BaseModel):
    execution_id: int
    chatbot_id: int
    message: InMessage

class ExecutionResponse(BaseModel):
    execution_id: int
    message: OutMessage
