from pydantic import BaseModel

class ChatBot(BaseModel):
    id: int
    name: str
    description: str
    user_id: int