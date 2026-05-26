from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.orm_models import SubgraphVersion, VersionStatusEnum


async def create_version(
    session: AsyncSession,
    owner_user_id: int,
    subgraph_name: str,
    author_id: int,
    s3_key: str,
    parent_id: Optional[int] = None,
    status: VersionStatusEnum = VersionStatusEnum.DRAFT,
) -> SubgraphVersion:
    version = SubgraphVersion(
        owner_user_id=owner_user_id,
        subgraph_name=subgraph_name,
        author_id=author_id,
        s3_key=s3_key,
        parent_id=parent_id,
        status=status,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


async def get_version(session: AsyncSession, version_id: int) -> Optional[SubgraphVersion]:
    return await session.get(SubgraphVersion, version_id)


async def get_latest_version(
    session: AsyncSession,
    owner_user_id: int,
    subgraph_name: str,
) -> Optional[SubgraphVersion]:
    """Самая свежая версия сабграфа `(owner_user_id, subgraph_name)`."""
    result = await session.execute(
        select(SubgraphVersion)
        .where(
            SubgraphVersion.owner_user_id == owner_user_id,
            SubgraphVersion.subgraph_name == subgraph_name,
        )
        .order_by(SubgraphVersion.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_versions(
    session: AsyncSession,
    owner_user_id: int,
    subgraph_name: str,
) -> list[SubgraphVersion]:
    """История всех версий сабграфа `(owner_user_id, subgraph_name)`, новые сверху."""
    result = await session.execute(
        select(SubgraphVersion)
        .where(
            SubgraphVersion.owner_user_id == owner_user_id,
            SubgraphVersion.subgraph_name == subgraph_name,
        )
        .order_by(SubgraphVersion.created_at.desc())
    )
    return list(result.scalars().all())


async def list_subgraph_names(session: AsyncSession, owner_user_id: int) -> list[str]:
    """Уникальные имена всех сабграфов пользователя — берётся хотя бы по одной версии."""
    result = await session.execute(
        select(SubgraphVersion.subgraph_name)
        .where(SubgraphVersion.owner_user_id == owner_user_id)
        .distinct()
    )
    return [row[0] for row in result.all()]


async def delete_subgraph(
    session: AsyncSession,
    owner_user_id: int,
    subgraph_name: str,
) -> int:
    """Удаляет все версии сабграфа. Возвращает число удалённых строк."""
    result = await session.execute(
        delete(SubgraphVersion).where(
            SubgraphVersion.owner_user_id == owner_user_id,
            SubgraphVersion.subgraph_name == subgraph_name,
        )
    )
    await session.commit()
    return result.rowcount or 0
