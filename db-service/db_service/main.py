from db.crud.user import create_user, list_users
from db.session import async_session_maker

import sys
import asyncio

async def test_crud():
    async with async_session_maker() as session:
        user = await create_user(session, "Вася", "vasya@example.com", "hash123")
        print("✅ Created:", user.id, user.name)
        users = await list_users(session)
        print("📦 All users:", users)


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    pass
    #asyncio.run(test_crud())
