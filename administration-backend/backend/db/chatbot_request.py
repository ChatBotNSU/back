import httpx
from typing import Optional

from config import get_config

config = get_config()

url = f"http://{config.db_service.host}:{config.db_service.port}/api/v1/chatbot"


async def get_chatbots(user_id: int):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/list", params={"user_id": user_id})
        r.raise_for_status()
    return r.json()


async def create_chatbot(user_id: int, chatbot_name: str, chatbot_description: str):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(
            f"{url}/create",
            params={"user_id": user_id, "name": chatbot_name, "description": chatbot_description},
        )
        r.raise_for_status()
    return r.json()


async def delete_chatbot(chatbot_id: int):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.delete(f"{url}/delete", params={"bot_id": chatbot_id})
        r.raise_for_status()
    return r.json()


async def create_version(
    chatbot_id: int,
    author_id: int,
    s3_key: str,
    parent_id: Optional[int] = None,
    status: str = "DRAFT",
) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(
            f"{url}/version",
            json={
                "chatbot_id": chatbot_id,
                "author_id":  author_id,
                "s3_key":     s3_key,
                "parent_id":  parent_id,
                "status":     status,
            },
        )
        r.raise_for_status()
    return r.json()


async def get_latest_version(chatbot_id: int) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/{chatbot_id}/versions/latest")
        if r.status_code == 404:
            return None
        r.raise_for_status()
    return r.json()


async def get_version(version_id: int) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/version/{version_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
    return r.json()


async def list_versions(chatbot_id: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/{chatbot_id}/versions")
        r.raise_for_status()
    return r.json()
