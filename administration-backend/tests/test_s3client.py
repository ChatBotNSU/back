"""Unit tests for minio_controller/S3Client.py."""

import pytest
import json
from unittest.mock import MagicMock, patch, mock_open
from io import BytesIO

from backend.minio_controller.S3Client import S3Client
from backend.models.chatbot import Chatbot


class TestS3ClientInit:
    """Tests for S3Client initialization."""

    def test_singleton_creation(self, mock_minio_client):
        # Given
        endpoint = "localhost:9000"
        access_key = "test_key"
        secret_key = "test_secret"

        # When
        S3Client._instance = None
        client = S3Client(endpoint, access_key, secret_key)

        # Then
        assert client is not None
        assert S3Client._instance is client

    def test_singleton_get_instance(self, mock_minio_client):
        # Given
        S3Client._instance = None
        S3Client("localhost:9000", "key", "secret")

        # When
        instance2 = S3Client.get_instance()

        # Then
        assert instance2 is not None

    def test_singleton_not_initialized(self):
        # Given
        S3Client._instance = None

        # When/Then
        with pytest.raises(RuntimeError, match="not initialized"):
            S3Client.get_instance()

    def test_init_creates_bucket_if_not_exists(self, mock_minio_client):
        # Given
        S3Client._instance = None
        mock_minio_client.bucket_exists.return_value = False

        # When
        S3Client("localhost:9000", "key", "secret")

        # Then
        mock_minio_client.bucket_exists.assert_called_once_with("chatbot-bucket")
        mock_minio_client.make_bucket.assert_called_once_with("chatbot-bucket")


class TestS3ClientUpload:
    """Tests for S3Client upload methods."""

    def test_upload_bytes(self, mock_minio_client):
        # Given
        S3Client._instance = None
        client = S3Client("localhost:9000", "key", "secret")
        data = b"test data"

        # When
        client.upload("test-obj", data)

        # Then
        mock_minio_client.put_object.assert_called_once()
        call_args = mock_minio_client.put_object.call_args
        assert call_args[0][1] == "test-obj"
        assert call_args[1]["length"] == len(data)

    def test_upload_chatbot(self, mock_minio_client):
        # Given
        S3Client._instance = None
        client = S3Client("localhost:9000", "key", "secret")
        chatbot = Chatbot(
            graph={"root": "node1", "nodes": {"node1": {"type": "text_answer", "assigned_variable": "var1", "next_node_id": "end"}}},
            subgraphs={},
            bot_id=1,
            bot_name="Test Bot"
        )

        # When
        client.upload_chatbot(1, chatbot)

        # Then
        mock_minio_client.put_object.assert_called_once()
        call_args = mock_minio_client.put_object.call_args
        assert call_args[0][1] == "chatbot-1.json"


class TestS3ClientDownload:
    """Tests for S3Client download methods."""

    def test_download_bytes(self, mock_minio_client):
        # Given
        S3Client._instance = None
        client = S3Client("localhost:9000", "key", "secret")
        mock_response = MagicMock()
        mock_response.read.return_value = b"test data"
        mock_minio_client.get_object.return_value = mock_response

        # When
        result = client.download("test-obj")

        # Then
        assert result == b"test data"
        mock_minio_client.get_object.assert_called_once_with("chatbot-bucket", "test-obj")

    def test_download_chatbot(self, mock_minio_client):
        # Given
        S3Client._instance = None
        client = S3Client("localhost:9000", "key", "secret")
        chatbot_data = {
            "bot_id": 1,
            "bot_name": "Test Bot",
            "graph": {"root": "node1", "nodes": {"node1": {"type": "text_answer", "assigned_variable": "var1", "next_node_id": "end"}}},
            "subgraphs": {}
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(chatbot_data).encode("utf-8")
        mock_minio_client.get_object.return_value = mock_response

        # When
        result = client.download_chatbot(1)

        # Then
        assert hasattr(result, 'bot_id')
        assert result.bot_id == 1
        assert result.bot_name == "Test Bot"
