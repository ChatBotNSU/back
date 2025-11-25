import httpx
from typing import List, Optional
from entities.ChatBot import ChatBot
from config import get_config

config = get_config()
url = f"http://{config.db_service.host}:{config.db_service.port}/api/v1/chatbot"

async def create_chatbot(name: str, description: str, user_id: int, key: str) -> ChatBot:
    async with httpx.AsyncClient(timeout=5.0) as client:
        data = {
            "name": name,
            "description": description,
            "user_id": user_id,
            "key": key
        }
        r = await client.post(f"{url}/", json=data)
        r.raise_for_status()
        result = r.json()
    
    return ChatBot(**result)

async def get_chatbot_by_name(chatbot_name: str, user_id: int) -> ChatBot:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(
            f"{url}/{chatbot_name}", 
            params={"user_id": user_id}
        )
        r.raise_for_status()
        result = r.json()
    
    return ChatBot(**result)

async def get_chatbots_by_user(user_id: int) -> List[ChatBot]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/{user_id}")
        r.raise_for_status()
        result = r.json()
    
    return [ChatBot(**bot_data) for bot_data in result]

async def delete_chatbot(chatbot_name: str, user_id: int) -> bool:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(
            f"{url}/delete", 
            params={"chatbot_name": chatbot_name, "user_id": user_id}
        )
        r.raise_for_status()
        result = r.json()
    
    return result

async def update_chatbot(chatbot_name: str, user_id: int, description: str) -> ChatBot:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.put(
            f"{url}/{chatbot_name}", 
            params={"user_id": user_id, "description": description}
        )
        r.raise_for_status()
        result = r.json()
    
    return ChatBot(**result)