from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException

from api.middleware import get_current_active_user
from entities.User import User
from entities.Graph import Graph
from db.graph_request import create_graph as db_create_graph
from db.graph_request import list_graphs as db_list_graphs
from db.graph_request import get_graph as db_get_graph
from db.graph_request import update_graph_s3_path as db_update_graph_s3_path
import httpx

router = APIRouter()

@router.post("/", response_model=Graph)
async def create_graph(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    s3_path: str | None = None,
):
    return await db_create_graph(name, s3_path)

@router.get("/", response_model=List[Graph])
async def list_graphs(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return await db_list_graphs()

@router.get("/{graph_id}", response_model=Graph)
async def get_graph(
    graph_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        return await db_get_graph(graph_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Graph with id {graph_id} not found")
        raise

@router.put("/{graph_id}/s3_path", response_model=Graph)
async def update_graph_s3_path(
    graph_id: int,
    s3_path: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        return await db_update_graph_s3_path(graph_id, s3_path)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Graph with id {graph_id} not found")
        raise