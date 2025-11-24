from pydantic import BaseModel
from typing import Optional, Dict, Any

class ChatBotCreate(BaseModel):
    name: str
    description: str
    user_id: int

class ChatBotRead(BaseModel):
    id: int
    name: str
    description: str
    user_id: int