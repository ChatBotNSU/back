from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.orm_models import ChatBot


async def create_chatbot(session: AsyncSession, name: str, description: str, user_id: int):
    bot = ChatBot(name=name, description=description, user_id=user_id)
    session.add(bot)
    await session.commit()
    await session.refresh(bot)
    return bot


async def get_chatbot(session: AsyncSession, name: str, user_id: int):
    return await session.execute(select(ChatBot).where(ChatBot.name == name and ChatBot.user_id == user_id))


async def list_chatbots_by_user(session: AsyncSession, user_id: int):
    result = await session.execute(select(ChatBot).where(ChatBot.user_id == user_id))
    return result.scalars().all()


async def delete_chatbot(session: AsyncSession, name: str, user_id: int):
    bot = await session.execute(select(ChatBot).where(ChatBot.name == name and ChatBot.user_id == user_id))
    if bot:
        await session.delete(bot)
        await session.commit()
        return True
    return False
