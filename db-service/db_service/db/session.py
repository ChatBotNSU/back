from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DB_URL", "postgresql+asyncpg://user:password@localhost:5432/mydb")

engine = create_async_engine(
    DB_URL,
    future=True,
    pool_pre_ping=True
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session() -> AsyncSession: # type: ignore
    async with async_session_maker() as session:
        yield session # type: ignore
