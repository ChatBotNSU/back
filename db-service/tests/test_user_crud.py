import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.crud.user import (
    create_user,
    get_user_by_id,
    get_user_by_email,
    list_users,
    delete_user
)
from db.orm_models import User


class TestCreateUser:
    """Тесты для функции create_user"""

    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_session, mock_user_data):
        """Тест успешного создания пользователя"""
        mock_user = MagicMock(spec=User)
        mock_user.id = mock_user_data["id"]
        mock_user.name = mock_user_data["name"]
        mock_user.email = mock_user_data["email"]
        
        result = await create_user(
            mock_session,
            mock_user_data["name"],
            mock_user_data["email"],
            mock_user_data["hashed_password"]
        )
        
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_user_called_with_correct_params(self, mock_session, mock_user_data):
        """Тест что create_user вызывается с правильными параметрами"""
        await create_user(
            mock_session,
            mock_user_data["name"],
            mock_user_data["email"],
            mock_user_data["hashed_password"]
        )
        
        call_args = mock_session.add.call_args
        user_obj = call_args[0][0]
        
        assert isinstance(user_obj, User)
        assert user_obj.name == mock_user_data["name"]
        assert user_obj.email == mock_user_data["email"]
        assert user_obj.hashed_password == mock_user_data["hashed_password"]


class TestGetUserById:
    """Тесты для функции get_user_by_id"""

    @pytest.mark.asyncio
    async def test_get_user_by_id_found(self, mock_session, mock_user_data):
        """Тест нахождения пользователя по ID"""
        mock_user = MagicMock(spec=User)
        mock_user.id = mock_user_data["id"]
        mock_session.get.return_value = mock_user
        
        result = await get_user_by_id(mock_session, mock_user_data["id"])
        
        mock_session.get.assert_awaited_once_with(User, mock_user_data["id"])
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, mock_session):
        """Тест когда пользователь не найден"""
        mock_session.get.return_value = None
        
        result = await get_user_by_id(mock_session, 999)
        
        mock_session.get.assert_awaited_once_with(User, 999)
        assert result is None


class TestGetUserByEmail:
    """Тесты для функции get_user_by_email"""

    @pytest.mark.asyncio
    async def test_get_user_by_email_found(self, mock_session, mock_user_data):
        """Тест нахождения пользователя по email"""
        mock_user = MagicMock(spec=User)
        mock_user.email = mock_user_data["email"]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result
        
        result = await get_user_by_email(mock_session, mock_user_data["email"])
        
        mock_session.execute.assert_awaited_once()
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self, mock_session):
        """Тест когда пользователь не найден по email"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        result = await get_user_by_email(mock_session, "notfound@example.com")
        
        assert result is None


class TestListUsers:
    """Тесты для функции list_users"""

    @pytest.mark.asyncio
    async def test_list_users_returns_all(self, mock_session, mock_user_data):
        """Тест получения списка всех пользователей"""
        mock_user1 = MagicMock(spec=User)
        mock_user2 = MagicMock(spec=User)
        
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_user1, mock_user2]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await list_users(mock_session)
        
        mock_session.execute.assert_awaited_once()
        assert len(result) == 2
        assert mock_user1 in result
        assert mock_user2 in result

    @pytest.mark.asyncio
    async def test_list_users_empty(self, mock_session):
        """Тест пустого списка пользователей"""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await list_users(mock_session)
        
        assert result == []


class TestDeleteUser:
    """Тесты для функции delete_user"""

    @pytest.mark.asyncio
    async def test_delete_user_success(self, mock_session, mock_user_data):
        """Тест успешного удаления пользователя"""
        mock_user = MagicMock(spec=User)
        mock_session.get.return_value = mock_user
        
        result = await delete_user(mock_session, mock_user_data["id"])
        
        mock_session.get.assert_awaited_once_with(User, mock_user_data["id"])
        mock_session.delete.assert_awaited_once_with(mock_user)
        mock_session.commit.assert_awaited_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, mock_session):
        """Тест когда пользователь не найден для удаления"""
        mock_session.get.return_value = None
        
        result = await delete_user(mock_session, 999)
        
        mock_session.get.assert_awaited_once_with(User, 999)
        mock_session.delete.assert_not_called()
        mock_session.commit.assert_not_called()
        assert result is False
