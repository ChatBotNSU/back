from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from db.crud.graph import create_graph, list_graphs, get_graph_by_id, update_graph_s3_path
from db.schemas.graph import GraphCreate, GraphRead

router = APIRouter()

@router.post("/", response_model=GraphRead)
async def create_graph_endpoint(graph: GraphCreate, session: AsyncSession = Depends(get_session)):
    new_graph = await create_graph(session, graph.name, graph.s3_path)
    return new_graph

@router.get("/", response_model=list[GraphRead])
async def list_graphs_endpoint(session: AsyncSession = Depends(get_session)):
    graphs = await list_graphs(session)
    return graphs

@router.get("/{graph_id}", response_model=GraphRead)
async def get_graph_endpoint(graph_id: int, session: AsyncSession = Depends(get_session)):
    graph = await get_graph_by_id(session, graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph with id {graph_id} not found")
    return graph

@router.put("/{graph_id}/s3_path", response_model=GraphRead)
async def update_graph_s3_path_endpoint(graph_id: int, s3_path: str, session: AsyncSession = Depends(get_session)):
    graph = await update_graph_s3_path(session, graph_id, s3_path)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph with id {graph_id} not found")
    return graph