from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.orm_models import ChatBot


async def create_chatbot(session: AsyncSession, name: str, description: str, user_id: int):
    bot = ChatBot(name=name, description=description, user_id=user_id)
    session.add(bot)
    await session.commit()
    await session.refresh(bot)
    return bot

async def update_chatbot(
    session: AsyncSession,
    bot_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
):
    bot = await session.get(ChatBot, bot_id)
    if bot is None:
        raise ValueError("Chatbot not found")

    if name is not None:
        bot.name = name
    if description is not None:
        bot.description = description

    await session.commit()
    await session.refresh(bot)
    return bot



async def get_chatbot(session: AsyncSession, bot_id: int):
    return await session.get(ChatBot, bot_id)


async def list_chatbots_by_user(session: AsyncSession, user_id: int):
    result = await session.execute(select(ChatBot).where(ChatBot.user_id == user_id))
    return result.scalars().all()


async def delete_chatbot(session: AsyncSession, bot_id: int):
    bot = await session.get(ChatBot, bot_id)
    if bot:
        await session.delete(bot)
        await session.commit()
        return True
    return False
