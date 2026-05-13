"""Unit tests for utils/token.py."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import jwt

from utils.token import create_access_token
from config import get_config


class TestCreateAccessToken:
    """Tests for create_access_token function."""

    def test_create_access_token_returns_string(self, mock_config):
        # Given
        data = {"sub": "test@example.com"}
        expires_delta = timedelta(minutes=30)

        with patch('utils.token.config', mock_config):
            # When
            result = create_access_token(data, expires_delta)

            # Then
            assert isinstance(result, str)
            assert len(result) > 0

    def test_create_access_token_contains_payload(self, mock_config):
        # Given
        email = "test@example.com"
        data = {"sub": email}
        expires_delta = timedelta(minutes=30)

        with patch('utils.token.config', mock_config):
            # When
            token = create_access_token(data, expires_delta)

            # Then
            decoded = jwt.decode(token, mock_config.authentication.secret_key,
                               algorithms=[mock_config.authentication.algorithm])
            assert decoded["sub"] == email

    def test_create_access_token_has_expiration(self, mock_config):
        # Given
        data = {"sub": "test@example.com"}
        expires_delta = timedelta(minutes=30)

        with patch('utils.token.config', mock_config):
            # When
            token = create_access_token(data, expires_delta)

            # Then
            decoded = jwt.decode(token, mock_config.authentication.secret_key,
                               algorithms=[mock_config.authentication.algorithm])
            assert "exp" in decoded
            assert isinstance(decoded["exp"], int)

    def test_create_access_token_expiration_time(self, mock_config):
        # Given
        data = {"sub": "test@example.com"}
        expires_delta = timedelta(minutes=30)
        now = datetime.now(timezone.utc)

        with patch('utils.token.config', mock_config):
            # When
            token = create_access_token(data, expires_delta)

            # Then
            decoded = jwt.decode(token, mock_config.authentication.secret_key,
                               algorithms=[mock_config.authentication.algorithm])
            exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
            expected_exp = now + expires_delta
            # Allow 1 second difference
            assert abs((exp_time - expected_exp).total_seconds()) < 1

    def test_create_access_token_no_expires_delta(self, mock_config):
        # Given
        data = {"sub": "test@example.com"}
        now = datetime.now(timezone.utc)

        with patch('utils.token.config', mock_config):
            # When
            token = create_access_token(data, expires_delta=None)

            # Then
            decoded = jwt.decode(token, mock_config.authentication.secret_key,
                               algorithms=[mock_config.authentication.algorithm])
            exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
            expected_exp = now + timedelta(minutes=15)
            assert abs((exp_time - expected_exp).total_seconds()) < 1

    def test_create_access_token_with_extra_data(self, mock_config):
        # Given
        data = {"sub": "test@example.com", "user_id": 123, "role": "admin"}
        expires_delta = timedelta(minutes=30)

        with patch('utils.token.config', mock_config):
            # When
            token = create_access_token(data, expires_delta)

            # Then
            decoded = jwt.decode(token, mock_config.authentication.secret_key,
                               algorithms=[mock_config.authentication.algorithm])
            assert decoded["user_id"] == 123
            assert decoded["role"] == "admin"
