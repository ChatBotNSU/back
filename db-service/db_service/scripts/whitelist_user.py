from pwdlib import PasswordHash

from db.crud.user import create_user, list_users
from db.session import async_session_maker

import asyncio

password_hash = PasswordHash.recommended()

async def create_whitelist_user():
    async with async_session_maker() as session:
        pwd_hash = password_hash.hash("hash123")
        user = await create_user(session, "Ваня", "Vanya@example.com", pwd_hash)
        user = await create_user(session, "Володя", "Vova@example.com", pwd_hash)
        user = await create_user(session, "Пайп", "Pipe@example.com", pwd_hash)
        user = await create_user(session, "Ильдар", "Ildar@example.com", pwd_hash)
        print("✅ Created:", user.id, user.name)
        users = await list_users(session)
        print("📦 All users:", users)

if __name__ == "__main__":
    asyncio.run(create_whitelist_user())
