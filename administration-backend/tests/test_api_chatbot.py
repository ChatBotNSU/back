"""Unit tests for api/chatbot.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

from entities.User import User


class TestReadChatbots:
    """Tests for read_chatbots endpoint."""

    @pytest.mark.asyncio
    async def test_read_chatbots_success(self):
        # Given
        current_user = User(id=1, name="Test", email="test@example.com", hashed_password="hash")
        mock_chatbots = [{"id": 1, "name": "Bot1"}, {"id": 2, "name": "Bot2"}]

        with patch('api.chatbot.get_chatbots', return_value=mock_chatbots):
            from api.chatbot import read_chatbots
            # When
            result = await read_chatbots(current_user)

            # Then
            assert result == mock_chatbots


class TestCreateChatbot:
    """Tests for create_chatbot endpoint."""

    @pytest.mark.asyncio
    async def test_create_chatbot_success(self):
        # Given
        from models.chatbot import ChatbotUnassigned, Graph, Variable
        current_user = User(id=1, name="Test", email="test@example.com", hashed_password="hash")
        
        chatbot_input = ChatbotUnassigned(
            variables=[],
            graph=Graph(root="node1", nodes={"node1": {"type": "text_answer", "assigned_variable": "var1", "next_node_id": "end"}}),
            bot_name="Test Bot"
        )
        mock_result = {"id": 1}

        with patch('api.chatbot.create_chatbot', return_value=mock_result):
            with patch('api.chatbot.S3Client') as mock_s3:
                mock_s3_instance = MagicMock()
                mock_s3.get_instance.return_value = mock_s3_instance
                
                from api.chatbot import create_chatbot_endpoint
                # When
                result = await create_chatbot_endpoint(chatbot_input, current_user)

                # Then
                assert result.bot_id == 1
                mock_s3_instance.upload_chatbot.assert_called_once()


class TestDeleteChatbot:
    """Tests for delete_chatbot endpoint."""

    @pytest.mark.asyncio
    async def test_delete_chatbot_success(self):
        # Given
        current_user = User(id=1, name="Test", email="test@example.com", hashed_password="hash")

        with patch('api.chatbot.delete_chatbot', return_value=None) as mock_delete:
            from api.chatbot import delete_chatbot_endpoint
            # When
            await delete_chatbot_endpoint(1, current_user)

            # Then
            mock_delete.assert_called_once_with(1)
