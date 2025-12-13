import httpx

from entities.User import User, UserHashedPassword
from utils.password import get_password_hash
from config import get_config

config = get_config()

url = f"http://{config.db_service.host}:{config.db_service.port}/api/v1/chatbot"


async def get_chatbots(user_id: int):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/list", params={"user_id": user_id})
        r.raise_for_status()
        result = r.json()
    
    print(result)
    return result

async def create_chatbot(user_id: int, chatbot_name: str, chatbot_description:str):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(f"{url}/create", params={"user_id": user_id, "name": chatbot_name, "description": chatbot_description})
        r.raise_for_status()
        result = r.json()
    
    print(result)
    return result


async def delete_chatbot(chatbot_id: int):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.delete(f"{url}/delete", params={"bot_id": chatbot_id})
        r.raise_for_status()
        result = r.json()
    
    print(result)
    return result
