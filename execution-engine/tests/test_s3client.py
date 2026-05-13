import pytest
from unittest.mock import patch, MagicMock, mock_open
import io

from minio_controller.S3Client import S3Client
from models.chatbot import Chatbot, Variable, Graph
from models.execution_state import ExecutionState


class TestS3ClientInit:
    """Tests for S3Client initialization"""

    @patch('minio_controller.S3Client.Minio')
    def test_s3_client_init(self, mock_minio_class):
        """Test S3Client initialization"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        assert client.bucket == "chatbot-bucket"
        mock_minio.bucket_exists.assert_called_once_with("chatbot-bucket")

    @patch('minio_controller.S3Client.Minio')
    def test_s3_client_creates_bucket_if_not_exists(self, mock_minio_class):
        """Test bucket creation when it doesn't exist"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = False
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        mock_minio.make_bucket.assert_called_once_with("chatbot-bucket")

    @patch('minio_controller.S3Client.Minio')
    def test_s3_client_singleton_pattern(self, mock_minio_class):
        """Test S3Client follows singleton pattern"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        # Reset singleton
        S3Client._instance = None

        client1 = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )
        client2 = S3Client.get_instance()

        assert client1 is client2

    def test_s3_client_get_instance_before_init(self):
        """Test get_instance raises error when not initialized"""
        S3Client._instance = None

        with pytest.raises(RuntimeError, match="S3Client not initialized"):
            S3Client.get_instance()


class TestS3ClientUpload:
    """Tests for S3Client upload operations"""

    @patch('minio_controller.S3Client.Minio')
    def test_upload_bytes(self, mock_minio_class):
        """Test uploading bytes data"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        test_data = b'{"key": "value"}'
        client.upload("test-object.json", test_data)

        mock_minio.put_object.assert_called_once()
        call_args = mock_minio.put_object.call_args
        assert call_args[0][1] == "test-object.json"
        assert call_args[1]["content_type"] == "application/json"

    @patch('minio_controller.S3Client.Minio')
    def test_upload_chatbot(self, mock_minio_class):
        """Test uploading chatbot object"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        chatbot = Chatbot(
            bot_id=1,
            bot_name="Test Bot",
            variables=[Variable(name="test_var", type="string")],
            graph=Graph(root="node_1", nodes={})
        )

        client.upload_chatbot(1, chatbot)

        mock_minio.put_object.assert_called_once()
        call_args = mock_minio.put_object.call_args
        assert call_args[0][1] == "chatbot-1.json"

    @patch('minio_controller.S3Client.Minio')
    def test_upload_execution(self, mock_minio_class):
        """Test uploading execution state"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        execution = ExecutionState(
            bot_id=1,
            execution_id=100,
            executing_node_id="node_1",
            variable_values={"var": "value"}
        )

        client.upload_execution(100, execution)

        mock_minio.put_object.assert_called_once()
        call_args = mock_minio.put_object.call_args
        assert call_args[0][1] == "execution-100.json"


class TestS3ClientDownload:
    """Tests for S3Client download operations"""

    @patch('minio_controller.S3Client.Minio')
    def test_download_bytes(self, mock_minio_class):
        """Test downloading bytes data"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"key": "value"}'
        mock_minio.get_object.return_value = mock_response

        data = client.download("test-object.json")

        assert data == b'{"key": "value"}'
        mock_minio.get_object.assert_called_once_with("chatbot-bucket", "test-object.json")

    @patch('minio_controller.S3Client.Minio')
    def test_download_chatbot(self, mock_minio_class):
        """Test downloading chatbot object"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        chatbot_json = Chatbot(
            bot_id=1,
            bot_name="Test Bot",
            variables=[Variable(name="test_var", type="string")],
            graph=Graph(root="node_1", nodes={})
        ).model_dump_json().encode("utf-8")

        mock_response = MagicMock()
        mock_response.read.return_value = chatbot_json
        mock_minio.get_object.return_value = mock_response

        chatbot = client.download_chatbot(1)

        assert isinstance(chatbot, Chatbot)
        assert chatbot.bot_id == 1
        assert chatbot.bot_name == "Test Bot"

    @patch('minio_controller.S3Client.Minio')
    def test_download_execution(self, mock_minio_class):
        """Test downloading execution state"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        client = S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        execution_json = ExecutionState(
            bot_id=1,
            execution_id=100,
            executing_node_id="node_1",
            variable_values={"var": "value"}
        ).model_dump_json().encode("utf-8")

        mock_response = MagicMock()
        mock_response.read.return_value = execution_json
        mock_minio.get_object.return_value = mock_response

        execution = client.download_execution(100)

        assert isinstance(execution, ExecutionState)
        assert execution.execution_id == 100
        assert execution.executing_node_id == "node_1"
