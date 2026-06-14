"""Unit tests for telegram-execution api/telegram_api.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Мокируем asyncio.create_task и aiogram до импорта
with patch('asyncio.create_task'):
    with patch('aiogram.Bot'):
        with patch('aiogram.Dispatcher'):
            from api.telegram_api import assigne, get_all, get, poller
            from fastapi import HTTPException


class TestTelegramApi:
    """Tests for telegram API endpoints."""

    @pytest.mark.asyncio
    async def test_assigne_endpoint(self):
        # Given
        token = "test_token_123"
        chatbot_id = 42

        with patch.object(poller, 'update_bots') as mock_update:
            # When
            result = await assigne(token=token, chatbot_id=chatbot_id)

            # Then
            mock_update.assert_called_once_with(token, chatbot_id)

    @pytest.mark.asyncio
    async def test_get_all_endpoint(self):
        # Given
        expected_bots = {"token1": 1, "token2": 2}

        with patch.object(poller, 'get_all', return_value=expected_bots) as mock_get:
            # When
            result = await get_all()

            # Then
            assert result == expected_bots
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_endpoint_exists(self):
        # Given
        token = "existing_token"
        expected_id = 123

        with patch.object(poller, 'get_by_token', return_value=expected_id) as mock_get:
            # When
            result = await get(token=token)

            # Then
            assert result == expected_id
            mock_get.assert_called_once_with(token)

    @pytest.mark.asyncio
    async def test_get_endpoint_not_found(self):
        # Given
        token = "unknown_token"

        with patch.object(poller, 'get_by_token', side_effect=HTTPException(status_code=404)):
            # When / Then
            with pytest.raises(HTTPException):
                await get(token=token)
