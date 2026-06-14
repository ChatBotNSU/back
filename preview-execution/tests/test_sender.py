"""Unit tests for preview-execution sender."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Мокируем asyncio.create_task до импорта чтобы избежать asyncio ошибок
with patch('asyncio.create_task'):
    from sender.preview_sender import PreviewResponseSender
    from models.redis_io_streams import ExecutionResponse, OutMessage


@pytest.fixture
def sender_instance():
    """Create a fresh PreviewResponseSender instance."""
    PreviewResponseSender._instance = None
    return PreviewResponseSender()


@pytest.fixture
def sample_response():
    """Sample ExecutionResponse for testing."""
    return ExecutionResponse(
        execution_id=42,
        message=OutMessage(text="Test response")
    )


class TestPreviewResponseSender:
    """Tests for PreviewResponseSender singleton and response handling."""

    # ==================== Singleton Tests ====================

    def test_singleton_creation(self, sender_instance):
        # When
        instance2 = PreviewResponseSender.get_instance()

        # Then
        assert instance2 is sender_instance

    def test_singleton_get_instance_error(self):
        # Given
        PreviewResponseSender._instance = None

        # When / Then
        with pytest.raises(RuntimeError, match="not initialized"):
            PreviewResponseSender.get_instance()

    # ==================== add_future Tests ====================

    @pytest.mark.asyncio
    async def test_add_future(self, sender_instance):
        # When
        future = await sender_instance.add_future(123)

        # Then
        assert isinstance(future, asyncio.Future)
        assert 123 in sender_instance._pending_responses
        assert sender_instance._pending_responses[123] is future

    @pytest.mark.asyncio
    async def test_add_future_multiple(self, sender_instance):
        # When
        future1 = await sender_instance.add_future(1)
        future2 = await sender_instance.add_future(2)
        future3 = await sender_instance.add_future(3)

        # Then
        assert len(sender_instance._pending_responses) == 3
        assert sender_instance._pending_responses[1] is future1
        assert sender_instance._pending_responses[2] is future2
        assert sender_instance._pending_responses[3] is future3

    @pytest.mark.asyncio
    async def test_concurrent_add_future(self, sender_instance):
        # Given
        async def add_future_task(exec_id):
            return await sender_instance.add_future(exec_id)

        # When
        tasks = [add_future_task(i) for i in range(10)]
        futures = await asyncio.gather(*tasks)

        # Then
        assert len(sender_instance._pending_responses) == 10
        assert all(isinstance(f, asyncio.Future) for f in futures)

    # ==================== send_response Tests ====================

    @pytest.mark.asyncio
    async def test_send_response_success(self, sender_instance, sample_response):
        # Given
        future = await sender_instance.add_future(42)

        # When
        result = await sender_instance.send_response(sample_response)

        # Then
        assert result is True
        assert future.done()
        assert future.result() == sample_response.message
        assert 42 not in sender_instance._pending_responses

    @pytest.mark.asyncio
    async def test_send_response_no_pending(self, sender_instance, sample_response):
        # When
        result = await sender_instance.send_response(sample_response)

        # Then
        assert result is False
        assert len(sender_instance._pending_responses) == 0

    @pytest.mark.asyncio
    async def test_send_response_already_done(self, sender_instance, sample_response):
        # Given
        future = await sender_instance.add_future(42)
        future.set_result(OutMessage(text="Already set"))

        # When
        result = await sender_instance.send_response(sample_response)

        # Then
        assert result is False
        assert 42 in sender_instance._pending_responses

    @pytest.mark.asyncio
    async def test_send_response_removes_only_matched_id(self, sender_instance):
        # Given
        future1 = await sender_instance.add_future(1)
        future2 = await sender_instance.add_future(2)

        response = ExecutionResponse(
            execution_id=1,
            message=OutMessage(text="Response 1")
        )

        # When
        result = await sender_instance.send_response(response)

        # Then
        assert result is True
        assert 1 not in sender_instance._pending_responses
        assert 2 in sender_instance._pending_responses
        assert sender_instance._pending_responses[2] is future2

    @pytest.mark.asyncio
    async def test_send_response_with_complex_message(self, sender_instance):
        # Given
        future = await sender_instance.add_future(999)

        response = ExecutionResponse(
            execution_id=999,
            message=OutMessage(
                text="Complex response",
                images=["img.png"],
                choise_options=["A", "B"]
            )
        )

        # When
        result = await sender_instance.send_response(response)

        # Then
        assert result is True
        assert future.done()
        result_msg = future.result()
        assert result_msg.text == "Complex response"
        assert result_msg.images == ["img.png"]
        assert result_msg.choise_options == ["A", "B"]
