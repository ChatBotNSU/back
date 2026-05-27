"""Unit tests for api/middleware.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException, status
from jwt.exceptions import InvalidTokenError

from backend.api.middleware import get_current_user, get_current_active_user
from backend.entities.User import User
from backend.entities.Token import TokenData


class TestGetCurrentUser:
    """Tests for get_current_user function."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_config):
        # Given
        token = "valid_token"
        mock_user = User(id=1, name="Test", email="test@example.com", hashed_password="hash")

        with patch('backend.api.middleware.jwt.decode', return_value={"sub": "test@example.com"}):
            with patch('backend.api.middleware.get_user', return_value=mock_user):
                with patch('backend.api.middleware.config', mock_config):
                    # When
                    result = await get_current_user(token)

                    # Then
                    assert result is mock_user

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_config):
        # Given
        token = "invalid_token"

        with patch('backend.api.middleware.jwt.decode', side_effect=InvalidTokenError()):
            with patch('backend.api.middleware.config', mock_config):
                # When/Then
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(token)

                assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
                assert exc_info.value.detail == "Could not validate credentials"

    @pytest.mark.asyncio
    async def test_get_current_user_no_username(self, mock_config):
        # Given
        token = "token_without_sub"

        with patch('backend.api.middleware.jwt.decode', return_value={}):
            with patch('backend.api.middleware.config', mock_config):
                # When/Then
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(token)

                assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_current_user_not_found(self, mock_config):
        # Given
        token = "valid_token"

        with patch('backend.api.middleware.jwt.decode', return_value={"sub": "test@example.com"}):
            with patch('backend.api.middleware.get_user', return_value=None):
                with patch('backend.api.middleware.config', mock_config):
                    # When/Then
                    with pytest.raises(HTTPException) as exc_info:
                        await get_current_user(token)

                    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetCurrentActiveUser:
    """Tests for get_current_active_user function."""

    @pytest.mark.asyncio
    async def test_get_current_active_user_success(self):
        # Given
        current_user = User(id=1, name="Test", email="test@example.com", hashed_password="hash")

        # When
        result = await get_current_active_user(current_user)

        # Then
        assert result is current_user

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self):
        # Given
        current_user = User(id=1, name="Test", email="test@example.com", hashed_password="hash")
        # Note: disabled field check is commented out in the code

        # When
        result = await get_current_active_user(current_user)

        # Then
        assert result is current_user
