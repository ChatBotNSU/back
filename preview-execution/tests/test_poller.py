"""Unit tests for preview-execution poller/preview_poller.py."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Мокируем asyncio.create_task до импорта
with patch('asyncio.create_task'):
    from poller.preview_poller import process_preview, get_execution_id, controller, poller
    from models.message import InMessage, OutMessage
    from models.redis_io_streams import ExecutionRequest, ExecutionResponse


class TestPreviewPoller:
    """Tests for preview poller endpoints."""

    @pytest.mark.asyncio
    async def test_process_preview_success(self):
        # Given
        chatbot_id = 100
        execution_id = 42
        message = InMessage(text="Test message")

        mock_future = asyncio.Future()
        mock_future.set_result(OutMessage(text="Response text"))

        with patch.object(poller, 'add_future', return_value=mock_future) as mock_add:
            with patch.object(controller, 'put_message') as mock_put:
                # When
                result = await process_preview(
                    chatbot_id=chatbot_id,
                    execution_id=execution_id,
                    message=message
                )

                # Then
                assert isinstance(result, OutMessage)
                assert result.text == "Response text"
                mock_add.assert_called_once_with(execution_id)
                mock_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_preview_with_images(self):
        # Given
        chatbot_id = 100
        execution_id = 43
        message = InMessage(text="Hello", images=["img.png"])

        mock_future = asyncio.Future()
        mock_future.set_result(OutMessage(
            text="Here is image",
            images=["result.png"]
        ))

        with patch.object(poller, 'add_future', return_value=mock_future):
            with patch.object(controller, 'put_message'):
                # When
                result = await process_preview(
                    chatbot_id=chatbot_id,
                    execution_id=execution_id,
                    message=message
                )

                # Then
                assert result.text == "Here is image"
                assert result.images == ["result.png"]

    @pytest.mark.asyncio
    async def test_process_preview_with_options(self):
        # Given
        chatbot_id = 100
        execution_id = 44
        message = InMessage(text="Choose")

        mock_future = asyncio.Future()
        mock_future.set_result(OutMessage(
            text="Select option",
            choise_options=["Option 1", "Option 2"]
        ))

        with patch.object(poller, 'add_future', return_value=mock_future):
            with patch.object(controller, 'put_message'):
                # When
                result = await process_preview(
                    chatbot_id=chatbot_id,
                    execution_id=execution_id,
                    message=message
                )

                # Then
                assert result.choise_options == ["Option 1", "Option 2"]

    @pytest.mark.asyncio
    async def test_process_preview_timeout(self):
        # Given
        chatbot_id = 100
        execution_id = 45
        message = InMessage(text="Test")

        mock_future = asyncio.Future()
        # Не устанавливаем результат - будет timeout

        with patch.object(poller, 'add_future', return_value=mock_future):
            with patch.object(controller, 'put_message'):
                # When / Then
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        process_preview(
                            chatbot_id=chatbot_id,
                            execution_id=execution_id,
                            message=message
                        ),
                        timeout=0.1
                    )

    @pytest.mark.asyncio
    async def test_get_execution_id(self):
        # Given
        expected_id = 123

        with patch.object(controller, 'get_execution_id', return_value=expected_id) as mock_get:
            # When
            result = await get_execution_id()

            # Then
            assert result == expected_id
            mock_get.assert_called_once()
