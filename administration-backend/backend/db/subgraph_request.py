import httpx
from typing import Optional

from config import get_config

config = get_config()

url = f"http://{config.db_service.host}:{config.db_service.port}/api/v1/subgraph"


async def create_version(
    owner_user_id: int,
    subgraph_name: str,
    author_id: int,
    s3_key: str,
    parent_id: Optional[int] = None,
    status: str = "DRAFT",
) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(
            f"{url}/version",
            json={
                "owner_user_id":  owner_user_id,
                "subgraph_name":  subgraph_name,
                "author_id":      author_id,
                "s3_key":         s3_key,
                "parent_id":      parent_id,
                "status":         status,
            },
        )
        r.raise_for_status()
    return r.json()


async def get_version(version_id: int) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/version/{version_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
    return r.json()


async def get_latest_version(owner_user_id: int, subgraph_name: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/{owner_user_id}/{subgraph_name}/versions/latest")
        if r.status_code == 404:
            return None
        r.raise_for_status()
    return r.json()


async def list_versions(owner_user_id: int, subgraph_name: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/{owner_user_id}/{subgraph_name}/versions")
        r.raise_for_status()
    return r.json()


async def list_subgraph_names(owner_user_id: int) -> list[str]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/{owner_user_id}/list")
        r.raise_for_status()
    return r.json()


async def delete_subgraph(owner_user_id: int, subgraph_name: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.delete(f"{url}/{owner_user_id}/{subgraph_name}")
        r.raise_for_status()
    return r.json()
