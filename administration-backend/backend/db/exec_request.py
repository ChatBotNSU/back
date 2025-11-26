import httpx
from typing import List, Optional, Dict, Any
from entities.Execution import Execution
from config import get_config

config = get_config()
url = f"http://{config.db_service.host}:{config.db_service.port}/api/v1/execution"

async def create_execution(chatbot_id: int, user_id: int) -> Execution:
    async with httpx.AsyncClient(timeout=5.0) as client:
        data = {
            "chatbot_id": chatbot_id,
            "user_id": user_id
        }
        r = await client.post(f"{url}/", json=data)
        r.raise_for_status()
        result = r.json()
    
    return Execution(**result)

async def update_execution(
    execution_id: str, 
    executing_node_id: Optional[int] = None, 
    variable_values: Optional[Dict[str, Any]] = None
) -> Execution:
    async with httpx.AsyncClient(timeout=5.0) as client:
        data = {}
        if executing_node_id is not None:
            data["executing_node_id"] = executing_node_id
        if variable_values is not None:
            data["variable_values"] = variable_values
            
        r = await client.put(
            f"{url}/{execution_id}", 
            json=data
        )
        r.raise_for_status()
        result = r.json()
    
    return Execution(**result)
