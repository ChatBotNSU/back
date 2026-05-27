"""Unit tests for telegram-execution controller/redis_streams.py."""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_config():
    """Mock configuration for RedisStreamsController."""
    config = MagicMock()
    config.redis.IOStream.stream_requests = "test_requests"
    config.redis.IOStream.stream_responses = "test_responses"
    config.redis.IOStream.group = "test_group"
    config.redis.IOStream.consumer = "test_consumer"
    return config


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    return redis


@pytest.fixture
def controller(mock_config, mock_redis, fresh_modules):
    """Create RedisStreamsController with mocked dependencies."""
    from controller.redis_streams import RedisStreamsController
    with patch('controller.redis_streams.get_config', return_value=mock_config):
        with patch('controller.redis_streams.get_redis', return_value=mock_redis):
            with patch('controller.redis_streams.TelegramResponseSender') as mock_sender:
                mock_sender_instance = MagicMock()
                mock_sender.get_instance.return_value = mock_sender_instance
                ctrl = RedisStreamsController()
                ctrl.redis = mock_redis
                ctrl.sender = mock_sender_instance
                return ctrl


class TestRedisStreamsControllerInit:
    """Tests for RedisStreamsController initialization."""

    def test_initialization(self, mock_config, mock_redis, fresh_modules):
        # Given
        from controller.redis_streams import RedisStreamsController
        with patch('controller.redis_streams.get_config', return_value=mock_config):
            with patch('controller.redis_streams.get_redis', return_value=mock_redis):
                with patch('controller.redis_streams.TelegramResponseSender'):
                    # When
                    ctrl = RedisStreamsController()

                    # Then
                    assert ctrl.stream_requests == "test_requests"
                    assert ctrl.stream_responses == "test_responses"
                    assert ctrl.group == "test_group"
                    assert ctrl.consumer == "test_consumer"

    def test_singleton_not_initialized(self, fresh_modules):
        # Given
        from controller.redis_streams import RedisStreamsController
        RedisStreamsController._instance = None

        # When / Then
        with pytest.raises(RuntimeError, match="not initialized"):
            RedisStreamsController.get_instance()

    def test_singleton_get_instance(self, controller, fresh_modules):
        # When
        from controller.redis_streams import RedisStreamsController
        instance = RedisStreamsController.get_instance()

        # Then
        assert instance is controller


class TestPutMessage:
    """Tests for put_message method."""

    @pytest.mark.asyncio
    async def test_put_message(self, controller, mock_redis, fresh_modules):
        # Given
        from models.redis_io_streams import ExecutionRequest, InMessage
        request = ExecutionRequest(
            execution_id=1,
            chatbot_id=100,
            message=InMessage(text="Test message")
        )

        # When
        await controller.put_message(request)

        # Then
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "test_requests"

        payload = call_args[0][1]["payload"]
        parsed = json.loads(payload)
        assert parsed["execution_id"] == 1
        assert parsed["chatbot_id"] == 100
        assert parsed["message"]["text"] == "Test message"

    @pytest.mark.asyncio
    async def test_put_message_with_restart(self, controller, mock_redis, fresh_modules):
        # Given
        from models.redis_io_streams import ExecutionRequest, InMessage
        request = ExecutionRequest(
            execution_id=2,
            chatbot_id=50,
            message=InMessage(text="/start", restart_command=True)
        )

        # When
        await controller.put_message(request)

        # Then
        payload = mock_redis.xadd.call_args[0][1]["payload"]
        parsed = json.loads(payload)
        assert parsed["message"]["restart_command"] is True
