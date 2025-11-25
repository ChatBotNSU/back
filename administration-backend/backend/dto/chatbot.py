from typing import List
from pydantic import BaseModel

class ChatBotCreateRequest(BaseModel):
    name: str
    description: str
    config: dict  # Конфигурация для сохранения в MinIO

class ChatBotUpdateRequest(BaseModel):
    description: str
    config: dict  # Обновленная конфигурация для MinIO

class ChatBotResponse(BaseModel):
    id: int
    name: str
    description: str
    user_id: int
    config: dict  # Конфигурация из MinIO

class ChatBotListResponse(BaseModel):
    chatbots: List[ChatBotResponse]