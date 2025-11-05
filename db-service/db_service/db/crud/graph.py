from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.orm_models import Graph

async def create_graph(session: AsyncSession, name: str, s3_path: str | None = None) -> Graph:
    graph = Graph(name=name, s3_path=s3_path)
    session.add(graph)
    await session.commit()
    await session.refresh(graph)
    return graph

async def list_graphs(session: AsyncSession) -> list[Graph]:
    result = await session.execute(select(Graph))
    return list(result.scalars().all())

async def get_graph_by_id(session: AsyncSession, graph_id: int) -> Graph | None:
    result = await session.execute(select(Graph).where(Graph.id == graph_id))
    return result.scalar_one_or_none()

async def update_graph_s3_path(session: AsyncSession, graph_id: int, s3_path: str) -> Graph | None:
    graph = await get_graph_by_id(session, graph_id)
    if graph:
        graph.s3_path = s3_path
        await session.commit()
        await session.refresh(graph)
    return graph