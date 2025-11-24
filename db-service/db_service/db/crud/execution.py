from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.orm_models import Execution

async def create_execution(session: AsyncSession, chatbot_id: int):
    exec_ = Execution(chatbot_id=chatbot_id)
    session.add(exec_)
    await session.commit()
    await session.refresh(exec_)
    return exec_


async def get_execution(session: AsyncSession, execution_id: int):
    return await session.get(Execution, execution_id)


async def list_executions_for_chatbot(session: AsyncSession, chatbot_id: int):
    result = await session.execute(select(Execution).where(Execution.chatbot_id == chatbot_id))
    return result.scalars().all()


async def update_execution_variables(session: AsyncSession, execution_id: int, variable_values: dict[str, str|int]):
    exec_ = await session.get(Execution, execution_id)
    if exec_:
        exec_.variable_values = variable_values
        await session.commit()
        await session.refresh(exec_)
    return exec_


async def delete_execution(session: AsyncSession, execution_id: int):
    exec_ = await session.get(Execution, execution_id)
    if exec_:
        await session.delete(exec_)
        await session.commit()
        return True
    return False
