from pydantic import BaseModel
from typing import Optional, Dict, Any

class ChatBotConfig(BaseModel):
    nodes: list
    edges: list
    variables: Optional[Dict[str, Any]] = None

class ChatBotCreate(BaseModel):
    name: str
    description: str
    user_id: int
    config: ChatBotConfig

class ChatBotRead(BaseModel):
    id: int
    name: str
    description: str
    user_id: int
    config: Optional[Dict[str, Any]] = None

class ChatBotUpdate(BaseModel):
    description: Optional[str] = None
    config: Optional[ChatBotConfig] = None