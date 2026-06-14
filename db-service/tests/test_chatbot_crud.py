import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.chatbot import (
    create_chatbot,
    update_chatbot,
    get_chatbot,
    list_chatbots_by_user,
    delete_chatbot
)
from db.orm_models import ChatBot


class TestCreateChatbot:
    """Тесты для функции create_chatbot"""

    @pytest.mark.asyncio
    async def test_create_chatbot_success(self, mock_session, mock_chatbot_data):
        """Тест успешного создания чатбота"""
        mock_bot = MagicMock(spec=ChatBot)
        mock_bot.id = mock_chatbot_data["id"]
        mock_bot.name = mock_chatbot_data["name"]
        
        result = await create_chatbot(
            mock_session,
            mock_chatbot_data["name"],
            mock_chatbot_data["description"],
            mock_chatbot_data["user_id"]
        )
        
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_chatbot_called_with_correct_params(self, mock_session, mock_chatbot_data):
        """Тест что create_chatbot вызывается с правильными параметрами"""
        await create_chatbot(
            mock_session,
            mock_chatbot_data["name"],
            mock_chatbot_data["description"],
            mock_chatbot_data["user_id"]
        )
        
        call_args = mock_session.add.call_args
        bot_obj = call_args[0][0]
        
        assert isinstance(bot_obj, ChatBot)
        assert bot_obj.name == mock_chatbot_data["name"]
        assert bot_obj.description == mock_chatbot_data["description"]
        assert bot_obj.user_id == mock_chatbot_data["user_id"]


class TestUpdateChatbot:
    """Тесты для функции update_chatbot"""

    @pytest.mark.asyncio
    async def test_update_chatbot_name_only(self, mock_session, mock_chatbot_data):
        """Тест обновления только имени чатбота"""
        mock_bot = MagicMock(spec=ChatBot)
        mock_bot.id = mock_chatbot_data["id"]
        mock_bot.name = "Updated Name"
        mock_bot.description = mock_chatbot_data["description"]
        mock_session.get.return_value = mock_bot
        
        result = await update_chatbot(mock_session, mock_chatbot_data["id"], name="Updated Name")
        
        mock_session.get.assert_awaited_once_with(ChatBot, mock_chatbot_data["id"])
        assert mock_bot.name == "Updated Name"
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        assert result == mock_bot

    @pytest.mark.asyncio
    async def test_update_chatbot_description_only(self, mock_session, mock_chatbot_data):
        """Тест обновления только описания чатбота"""
        mock_bot = MagicMock(spec=ChatBot)
        mock_bot.id = mock_chatbot_data["id"]
        mock_bot.name = mock_chatbot_data["name"]
        mock_bot.description = "Updated Description"
        mock_session.get.return_value = mock_bot
        
        result = await update_chatbot(mock_session, mock_chatbot_data["id"], description="Updated Description")
        
        assert mock_bot.description == "Updated Description"
        assert result == mock_bot

    @pytest.mark.asyncio
    async def test_update_chatbot_not_found(self, mock_session):
        """Тест когда чатбот не найден для обновления"""
        mock_session.get.return_value = None
        
        with pytest.raises(ValueError, match="Chatbot not found"):
            await update_chatbot(mock_session, 999, name="New Name")
        
        mock_session.get.assert_awaited_once_with(ChatBot, 999)
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_chatbot_both_fields(self, mock_session, mock_chatbot_data):
        """Тест обновления обоих полей"""
        mock_bot = MagicMock(spec=ChatBot)
        mock_bot.id = mock_chatbot_data["id"]
        mock_session.get.return_value = mock_bot
        
        await update_chatbot(
            mock_session,
            mock_chatbot_data["id"],
            name="New Name",
            description="New Description"
        )
        
        assert mock_bot.name == "New Name"
        assert mock_bot.description == "New Description"


class TestGetChatbot:
    """Тесты для функции get_chatbot"""

    @pytest.mark.asyncio
    async def test_get_chatbot_found(self, mock_session, mock_chatbot_data):
        """Тест нахождения чатбота по ID"""
        mock_bot = MagicMock(spec=ChatBot)
        mock_bot.id = mock_chatbot_data["id"]
        mock_session.get.return_value = mock_bot
        
        result = await get_chatbot(mock_session, mock_chatbot_data["id"])
        
        mock_session.get.assert_awaited_once_with(ChatBot, mock_chatbot_data["id"])
        assert result == mock_bot

    @pytest.mark.asyncio
    async def test_get_chatbot_not_found(self, mock_session):
        """Тест когда чатбот не найден"""
        mock_session.get.return_value = None
        
        result = await get_chatbot(mock_session, 999)
        
        mock_session.get.assert_awaited_once_with(ChatBot, 999)
        assert result is None


class TestListChatbotsByUser:
    """Тесты для функции list_chatbots_by_user"""

    @pytest.mark.asyncio
    async def test_list_chatbots_by_user_returns_all(self, mock_session, mock_chatbot_data):
        """Тест получения списка всех чатботов пользователя"""
        mock_bot1 = MagicMock(spec=ChatBot)
        mock_bot2 = MagicMock(spec=ChatBot)
        
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_bot1, mock_bot2]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await list_chatbots_by_user(mock_session, mock_chatbot_data["user_id"])
        
        mock_session.execute.assert_awaited_once()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_chatbots_by_user_empty(self, mock_session):
        """Тест пустого списка чатботов"""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await list_chatbots_by_user(mock_session, 1)
        
        assert result == []


class TestDeleteChatbot:
    """Тесты для функции delete_chatbot"""

    @pytest.mark.asyncio
    async def test_delete_chatbot_success(self, mock_session, mock_chatbot_data):
        """Тест успешного удаления чатбота"""
        mock_bot = MagicMock(spec=ChatBot)
        mock_session.get.return_value = mock_bot
        
        result = await delete_chatbot(mock_session, mock_chatbot_data["id"])
        
        mock_session.get.assert_awaited_once_with(ChatBot, mock_chatbot_data["id"])
        mock_session.delete.assert_awaited_once_with(mock_bot)
        mock_session.commit.assert_awaited_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_chatbot_not_found(self, mock_session):
        """Тест когда чатбот не найден для удаления"""
        mock_session.get.return_value = None
        
        result = await delete_chatbot(mock_session, 999)
        
        mock_session.get.assert_awaited_once_with(ChatBot, 999)
        mock_session.delete.assert_not_called()
        mock_session.commit.assert_not_called()
        assert result is False
