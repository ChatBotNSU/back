from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.orm_models import ChatBot, ChatbotVersion, VersionStatusEnum


async def create_chatbot(session: AsyncSession, name: str, description: str, user_id: int) -> ChatBot:
    bot = ChatBot(name=name, description=description, user_id=user_id)
    session.add(bot)
    await session.commit()
    await session.refresh(bot)
    return bot


async def get_chatbot(session: AsyncSession, bot_id: int) -> Optional[ChatBot]:
    return await session.get(ChatBot, bot_id)


async def list_chatbots_by_user(session: AsyncSession, user_id: int) -> list[ChatBot]:
    result = await session.execute(select(ChatBot).where(ChatBot.user_id == user_id))
    return list(result.scalars().all())


async def delete_chatbot(session: AsyncSession, bot_id: int) -> bool:
    bot = await session.get(ChatBot, bot_id)
    if bot:
        await session.delete(bot)
        await session.commit()
        return True
    return False


async def create_version(
    session: AsyncSession,
    chatbot_id: int,
    author_id: int,
    s3_key: str,
    parent_id: Optional[int] = None,
    status: VersionStatusEnum = VersionStatusEnum.DRAFT,
) -> ChatbotVersion:
    version = ChatbotVersion(
        chatbot_id=chatbot_id,
        author_id=author_id,
        s3_key=s3_key,
        parent_id=parent_id,
        status=status,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


async def get_version(session: AsyncSession, version_id: int) -> Optional[ChatbotVersion]:
    return await session.get(ChatbotVersion, version_id)


async def get_latest_version(session: AsyncSession, chatbot_id: int) -> Optional[ChatbotVersion]:
    """Возвращает самую новую версию бота по created_at."""
    result = await session.execute(
        select(ChatbotVersion)
        .where(ChatbotVersion.chatbot_id == chatbot_id)
        .order_by(ChatbotVersion.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_versions(session: AsyncSession, chatbot_id: int) -> list[ChatbotVersion]:
    """Возвращает историю версий от новой к старой."""
    result = await session.execute(
        select(ChatbotVersion)
        .where(ChatbotVersion.chatbot_id == chatbot_id)
        .order_by(ChatbotVersion.created_at.desc())
    )
    return list(result.scalars().all())
