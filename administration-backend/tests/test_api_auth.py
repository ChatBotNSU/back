"""Unit tests for api/auth.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from api.auth import login_for_access_token, authenticate_user


class TestAuthenticateUser:
    """Tests for authenticate_user function."""

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self):
        # Given
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.hashed_password = "hashed_password"

        with patch('api.auth.get_user', return_value=mock_user):
            with patch('api.auth.verify_password', return_value=True):
                # When
                result = await authenticate_user("test@example.com", "password123")

                # Then
                assert result is mock_user

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        # Given
        with patch('api.auth.get_user', return_value=None):
            # When
            result = await authenticate_user("unknown@example.com", "password")

            # Then
            assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self):
        # Given
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.hashed_password = "hashed_password"

        with patch('api.auth.get_user', return_value=mock_user):
            with patch('api.auth.verify_password', return_value=False):
                # When
                result = await authenticate_user("test@example.com", "wrong_password")

                # Then
                assert result is None


class TestLoginForAccessToken:
    """Tests for login_for_access_token endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self):
        # Given
        mock_user = MagicMock()
        mock_user.email = "test@example.com"

        form_data = MagicMock(spec=OAuth2PasswordRequestForm)
        form_data.username = "test@example.com"
        form_data.password = "password123"

        with patch('api.auth.authenticate_user', return_value=mock_user):
            with patch('api.auth.create_access_token', return_value="fake_token"):
                # When
                result = await login_for_access_token(form_data)

                # Then
                assert result.access_token == "fake_token"
                assert result.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_login_failure_wrong_credentials(self):
        # Given
        form_data = MagicMock(spec=OAuth2PasswordRequestForm)
        form_data.username = "test@example.com"
        form_data.password = "wrong_password"

        with patch('api.auth.authenticate_user', return_value=None):
            # When/Then
            with pytest.raises(HTTPException) as exc_info:
                await login_for_access_token(form_data)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "Incorrect username or password"
