import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from redis.exceptions import ResponseError

from redis_controller.redis import get_redis
from redis_controller.redis_loop import redis_router
from models import ExecutionRequest, ExecutionResponse
from models.message import OutMessage


class TestRedisConnection:
    """Tests for redis.py"""

    @patch('redis_controller.redis.Redis')
    def test_get_redis_creates_connection(self, mock_redis_class):
        """Test get_redis creates Redis connection"""
        mock_instance = MagicMock()
        mock_redis_class.return_value = mock_instance

        with patch('redis_controller.redis.get_config') as mock_get_config:
            mock_get_config.return_value = MagicMock(
                redis=MagicMock(host="localhost", port=6379)
            )

            # Reset cached connection
            import redis_controller.redis as redis_module
            redis_module._redis = None

            result = get_redis()

            assert result is mock_instance
            mock_redis_class.assert_called_once_with(
                host="localhost",
                port=6379,
                decode_responses=True
            )

    def test_get_redis_returns_cached_connection(self):
        """Test get_redis returns cached connection"""
        mock_cached = MagicMock()

        with patch('redis_controller.redis._redis', mock_cached):
            with patch('redis_controller.redis.Redis') as mock_redis_class:
                result = get_redis()
                assert result is mock_cached
                mock_redis_class.assert_not_called()


class TestRedisLoop:
    """Tests for redis_loop.py"""

    @pytest.mark.asyncio
    async def test_redis_router_creates_consumer_groups(self):
        """Test redis_router creates consumer groups"""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        async def mock_processor(request):
            return ExecutionResponse(
                execution_id=1,
                message=OutMessage(text="Processed", images=[], audios=[], files=[], choise_options=[])
            )

        with patch('redis_controller.redis_loop.get_redis', return_value=mock_redis):
            with patch('redis_controller.redis_loop.get_config') as mock_get_config:
                mock_get_config.return_value = MagicMock(
                    redis=MagicMock(
                        IOStream=MagicMock(
                            stream_requests="requests",
                            stream_responses="responses",
                            group="test-group",
                            consumer="test-consumer"
                        )
                    )
                )
                # Stop after first iteration
                mock_redis.xreadgroup = AsyncMock(side_effect=asyncio.CancelledError())

                with pytest.raises(asyncio.CancelledError):
                    await redis_router(mock_processor)

                # Check consumer groups were created (twice - for requests and responses)
                assert mock_redis.xgroup_create.call_count == 2

    @pytest.mark.asyncio
    async def test_redis_router_handles_busygroup_error(self):
        """Test redis_router handles BUSYGROUP error"""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock(side_effect=ResponseError("BUSYGROUP"))
        
        async def mock_processor(request):
            return ExecutionResponse(
                execution_id=1,
                message=OutMessage(text="Processed", images=[], audios=[], files=[], choise_options=[])
            )

        with patch('redis_controller.redis_loop.get_redis', return_value=mock_redis):
            with patch('redis_controller.redis_loop.get_config') as mock_get_config:
                mock_get_config.return_value = MagicMock(
                    redis=MagicMock(
                        IOStream=MagicMock(
                            stream_requests="requests",
                            stream_responses="responses",
                            group="test-group",
                            consumer="test-consumer"
                        )
                    )
                )
                # Stop after first iteration
                mock_redis.xreadgroup = AsyncMock(side_effect=asyncio.CancelledError())

                with pytest.raises(asyncio.CancelledError):
                    await redis_router(mock_processor)

                # Should be called twice (for both streams)
                assert mock_redis.xgroup_create.call_count == 2

    @pytest.mark.asyncio
    async def test_redis_router_processes_request(self):
        """Test redis_router processes incoming request"""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        request_data = {
            "execution_id": 1,
            "chatbot_id": 1,
            "user_id": 123,
            "message": {"text": "Hello"}
        }

        mock_response = ExecutionResponse(
            execution_id=1,
            message=OutMessage(text="Processed", images=[], audios=[], files=[], choise_options=[])
        )

        mock_redis.xreadgroup = AsyncMock(return_value=[
            ("requests", [
                ("msg_id_1", {"payload": json.dumps(request_data)})
            ])
        ])
        mock_redis.xadd = AsyncMock()
        mock_redis.xack = AsyncMock(side_effect=asyncio.CancelledError())

        async def mock_processor(request):
            assert request.execution_id == 1
            return mock_response

        with patch('redis_controller.redis_loop.get_redis', return_value=mock_redis):
            with patch('redis_controller.redis_loop.get_config') as mock_get_config:
                mock_get_config.return_value = MagicMock(
                    redis=MagicMock(
                        IOStream=MagicMock(
                            stream_requests="requests",
                            stream_responses="responses",
                            group="test-group",
                            consumer="test-consumer"
                        )
                    )
                )
                with pytest.raises(asyncio.CancelledError):
                    await redis_router(mock_processor)

                mock_redis.xadd.assert_called_once()
                mock_redis.xack.assert_called_once_with("requests", "test-group", "msg_id_1")

    @pytest.mark.asyncio
    async def test_redis_router_handles_invalid_json(self):
        """Test redis_router handles invalid JSON"""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        async def mock_processor(request):
            return ExecutionResponse(execution_id=1, message=OutMessage(text="OK", images=[], audios=[], files=[], choise_options=[]))

        with patch('redis_controller.redis_loop.get_redis', return_value=mock_redis):
            with patch('redis_controller.redis_loop.get_config') as mock_get_config:
                mock_get_config.return_value = MagicMock(
                    redis=MagicMock(
                        IOStream=MagicMock(
                            stream_requests="requests",
                            stream_responses="responses",
                            group="test-group",
                            consumer="test-consumer"
                        )
                    )
                )
                # Return invalid JSON then stop
                mock_redis.xreadgroup = AsyncMock(side_effect=[
                    [("requests", [("msg_id_1", {"payload": "invalid json"})])],
                    asyncio.CancelledError()
                ])
                mock_redis.xadd = AsyncMock()

                with pytest.raises(asyncio.CancelledError):
                    await redis_router(mock_processor)

                # Should not add response for invalid JSON
                mock_redis.xadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_router_handles_no_request(self):
        """Test redis_router handles no incoming request"""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        async def mock_processor(request):
            return ExecutionResponse(execution_id=1, message=OutMessage(text="OK", images=[], audios=[], files=[], choise_options=[]))

        with patch('redis_controller.redis_loop.get_redis', return_value=mock_redis):
            with patch('redis_controller.redis_loop.get_config') as mock_get_config:
                mock_get_config.return_value = MagicMock(
                    redis=MagicMock(
                        IOStream=MagicMock(
                            stream_requests="requests",
                            stream_responses="responses",
                            group="test-group",
                            consumer="test-consumer"
                        )
                    )
                )
                # Return None twice then raise CancelledError
                mock_redis.xreadgroup = AsyncMock(side_effect=[None, asyncio.CancelledError()])

                with pytest.raises(asyncio.CancelledError):
                    await redis_router(mock_processor)
