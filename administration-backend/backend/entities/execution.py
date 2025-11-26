from pydantic import BaseModel
from typing import Dict, Any

class Execution(BaseModel):
    id: str
    chatbot_id: int
    executing_node_id: int
    variable_values: Dict[str, Any]