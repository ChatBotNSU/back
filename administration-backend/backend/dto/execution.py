from pydantic import BaseModel
from typing import Dict, Any, Optional

class ExecutionCreate(BaseModel):
    chatbot_id: int
    user_id: int

class ExecutionUpdate(BaseModel):
    executing_node_id: Optional[int] = None
    variable_values: Optional[Dict[str, Any]] = None

class ExecutionRead(BaseModel):
    id: str
    chatbot_id: int
    executing_node_id: int
    variable_values: Dict[str, Any]
