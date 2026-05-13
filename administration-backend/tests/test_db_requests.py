"""Unit tests for db/user_request.py and db/chatbot_request.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from entities.User import User


class TestGetUser:
    """Tests for get_user function."""

    @pytest.mark.asyncio
    async def test_get_user_by_email_success(self):
        # Given
        email = "test@example.com"
        mock_response_data = {
            "id": 1,
            "name": "Test User",
            "email": email,
            "hashed_password": "hashed_pwd"
        }

        mock_response = MagicMock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch('db.user_request.httpx.AsyncClient', return_value=mock_client):
            from db.user_request import get_user
            # When
            result = await get_user(email=email)

            # Then
            assert isinstance(result, User)
            assert result.email == email
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_no_params_error(self):
        # Given/When/Then
        from db.user_request import get_user
        with pytest.raises(Exception, match="both None"):
            await get_user(email=None, password=None)


class TestChatbotRequests:
    """Tests for chatbot request functions."""

    @pytest.mark.asyncio
    async def test_get_chatbots_success(self):
        # Given
        user_id = 1
        mock_response_data = [{"id": 1, "name": "Bot1"}]

        mock_response = MagicMock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch('db.chatbot_request.httpx.AsyncClient', return_value=mock_client):
            from db.chatbot_request import get_chatbots
            # When
            result = await get_chatbots(user_id)

            # Then
            assert result == mock_response_data
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_chatbot_success(self):
        # Given
        user_id = 1
        name = "Test Bot"
        description = "Test Description"
        mock_response_data = {"id": 1, "name": name}

        mock_response = MagicMock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch('db.chatbot_request.httpx.AsyncClient', return_value=mock_client):
            from db.chatbot_request import create_chatbot
            # When
            result = await create_chatbot(user_id, name, description)

            # Then
            assert result == mock_response_data
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_chatbot_success(self):
        # Given
        chatbot_id = 1
        mock_response_data = {"deleted": True}

        mock_response = MagicMock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch('db.chatbot_request.httpx.AsyncClient', return_value=mock_client):
            from db.chatbot_request import delete_chatbot
            # When
            result = await delete_chatbot(chatbot_id)

            # Then
            assert result == mock_response_data
            mock_client.delete.assert_called_once()
