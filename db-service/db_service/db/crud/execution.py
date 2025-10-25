from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.orm_models import TelegramExecution, TelegramExecutionStatusEnum


async def create_execution(session: AsyncSession, chatbot_id: int, status: TelegramExecutionStatusEnum):
    exec_ = TelegramExecution(chatbot_id=chatbot_id, status=status)
    session.add(exec_)
    await session.commit()
    await session.refresh(exec_)
    return exec_


async def get_execution(session: AsyncSession, execution_id: int):
    return await session.get(TelegramExecution, execution_id)


async def list_executions_for_chatbot(session: AsyncSession, chatbot_id: int):
    result = await session.execute(select(TelegramExecution).where(TelegramExecution.chatbot_id == chatbot_id))
    return result.scalars().all()


async def update_execution_status(session: AsyncSession, execution_id: int, new_status: TelegramExecutionStatusEnum):
    exec_ = await session.get(TelegramExecution, execution_id)
    if exec_:
        exec_.status = new_status
        await session.commit()
        await session.refresh(exec_)
    return exec_


async def delete_execution(session: AsyncSession, execution_id: int):
    exec_ = await session.get(TelegramExecution, execution_id)
    if exec_:
        await session.delete(exec_)
        await session.commit()
        return True
    return False
