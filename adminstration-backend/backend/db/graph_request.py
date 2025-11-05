import httpx
from typing import List

from entities.Graph import Graph
from config import get_config

config = get_config()

url = f"http://{config.db_service.host}:{config.db_service.port}/api/v1/graph"

async def create_graph(name: str, s3_path: str | None = None) -> Graph:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(url, json={"name": name, "s3_path": s3_path})
        r.raise_for_status()
        return Graph(**r.json())

async def list_graphs() -> List[Graph]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return [Graph(**g) for g in r.json()]

async def get_graph(graph_id: int) -> Graph:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/{graph_id}")
        r.raise_for_status()
        return Graph(**r.json())

async def update_graph_s3_path(graph_id: int, s3_path: str) -> Graph:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.put(f"{url}/{graph_id}/s3_path", params={"s3_path": s3_path})
        r.raise_for_status()
        return Graph(**r.json())