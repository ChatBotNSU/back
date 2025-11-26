from typing import List
from pydantic import BaseModel

class ChatBotCreateRequest(BaseModel):
    name: str
    description: str
    config: dict

class ChatBotUpdateRequest(BaseModel):
    description: str
    config: dict

class ChatBotResponse(BaseModel):
    id: int
    name: str
    description: str
    user_id: int
    config: dict

class ChatBotListResponse(BaseModel):
    chatbots: List[ChatBotResponse]