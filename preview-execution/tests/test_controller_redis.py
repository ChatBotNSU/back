"""Unit tests for preview-execution controller/redis.py."""

import pytest
from unittest.mock import patch, MagicMock

# Мокируем controller/__init__.py до импорта чтобы избежать asyncio.create_task()
with patch('asyncio.create_task'):
    from controller.redis import get_redis


class TestGetRedis:
    """Tests for get_redis function."""

    def setup_method(self):
        """Reset global _redis before each test."""
        import controller.redis as redis_module
        redis_module._redis = None

    @patch('controller.redis.Redis')
    @patch('controller.redis.get_config')
    def test_get_redis_creates_connection(self, mock_get_config, mock_redis_class):
        # Given
        mock_config = MagicMock()
        mock_config.redis.host = "localhost"
        mock_config.redis.port = 6379
        mock_get_config.return_value = mock_config

        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance

        # When
        result = get_redis()

        # Then
        mock_redis_class.assert_called_once_with(
            host="localhost",
            port=6379,
            decode_responses=True
        )
        assert result is mock_redis_instance

    @patch('controller.redis.Redis')
    @patch('controller.redis.get_config')
    def test_get_redis_reuses_connection(self, mock_get_config, mock_redis_class):
        # Given
        mock_config = MagicMock()
        mock_config.redis.host = "localhost"
        mock_config.redis.port = 6379
        mock_get_config.return_value = mock_config

        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance

        # When
        first_call = get_redis()
        second_call = get_redis()

        # Then
        mock_redis_class.assert_called_once()
        assert first_call is second_call
        assert first_call is mock_redis_instance

    @patch('controller.redis.Redis')
    @patch('controller.redis.get_config')
    def test_get_redis_uses_config_values(self, mock_get_config, mock_redis_class):
        # Given
        mock_config = MagicMock()
        mock_config.redis.host = "redis-server"
        mock_config.redis.port = 6380
        mock_get_config.return_value = mock_config

        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance

        # When
        get_redis()

        # Then
        mock_redis_class.assert_called_once_with(
            host="redis-server",
            port=6380,
            decode_responses=True
        )
