from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.orm_models import User


async def create_user(session: AsyncSession, name: str, email: str, hashed_password: str):
    user = User(name=name, email=email, hashed_password=hashed_password)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: int):
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str):
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def list_users(session: AsyncSession):
    result = await session.execute(select(User))
    return result.scalars().all()


async def delete_user(session: AsyncSession, user_id: int):
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
        await session.commit()
        return True
    return False
