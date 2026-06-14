import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    """Фикстура для мока AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.scalars = MagicMock()
    session.scalar = MagicMock()
    return session


@pytest.fixture
def mock_user_data():
    """Фикстура с тестовыми данными пользователя"""
    return {
        "id": 1,
        "name": "Test User",
        "email": "test@example.com",
        "hashed_password": "hashed123"
    }


@pytest.fixture
def mock_chatbot_data():
    """Фикстура с тестовыми данными чатбота"""
    return {
        "id": 1,
        "name": "Test Chatbot",
        "description": "Test Description",
        "user_id": 1
    }
