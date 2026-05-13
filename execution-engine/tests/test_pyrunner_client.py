import pytest
from unittest.mock import MagicMock, patch
import httpx

from sandbox_runner.client import PyRunnerClient, DEFAULT_URL
from sandbox_runner.schemas import RunResponse, RunRequest


class TestPyRunnerClientInit:
    """Tests for PyRunnerClient initialization"""

    def test_init_default_url(self):
        """Test initialization with default URL"""
        client = PyRunnerClient()

        assert client.base_url == DEFAULT_URL.rstrip("/")
        assert client.timeout == 15.0

    def test_init_custom_url(self):
        """Test initialization with custom URL"""
        client = PyRunnerClient(base_url="http://custom:8080/run", timeout=30.0)

        assert client.base_url == "http://custom:8080/run"
        assert client.timeout == 30.0

    def test_init_url_trailing_slash(self):
        """Test initialization strips trailing slash"""
        client = PyRunnerClient(base_url="http://custom:8080/run/")

        assert client.base_url == "http://custom:8080/run"


class TestPyRunnerClientRun:
    """Tests for PyRunnerClient.run method"""

    def test_run_success(self):
        """Test successful run"""
        client = PyRunnerClient(base_url="http://test:8080/run")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "job_id": "test-job",
            "status": "OK",
            "variables": {"x": 5},
            "added_variables": {"result": 10},
            "removed_variables": [],
            "logs": {"stdout": "", "stderr": ""},
            "metrics": {"wall_ms": 100}
        }

        with patch('httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            response = client.run(
                code="result = x * 2",
                variables={"x": 5},
                schema={"x": "int", "result": "int"},
                job_id="test-job"
            )

            assert response.job_id == "test-job"
            assert response.status == "OK"
            assert response.variables == {"x": 5}

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "http://test:8080/run"

    def test_run_with_allow_imports(self):
        """Test run with custom allowed imports"""
        client = PyRunnerClient(base_url="http://test:8080/run")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "job_id": "test-job",
            "status": "OK",
            "variables": None,
            "added_variables": {},
            "removed_variables": [],
            "logs": {"stdout": "", "stderr": ""},
            "metrics": {"wall_ms": 100}
        }

        with patch('httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            client.run(
                code="import numpy",
                variables={},
                schema={},
                allow_imports=["numpy", "pandas"]
            )

            call_args = mock_client.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["package_policy"]["allow_imports"] == ["numpy", "pandas"]

    def test_run_http_error(self):
        """Test run with HTTP error"""
        client = PyRunnerClient(base_url="http://test:8080/run")

        with patch('httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500)
            )

            with pytest.raises(httpx.HTTPStatusError):
                client.run(
                    code="raise Exception()",
                    variables={},
                    schema={}
                )

    def test_run_generates_job_id(self):
        """Test run generates UUID if job_id not provided"""
        client = PyRunnerClient(base_url="http://test:8080/run")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "job_id": "generated-uuid",
            "status": "OK",
            "variables": None,
            "added_variables": {},
            "removed_variables": [],
            "logs": {"stdout": "", "stderr": ""},
            "metrics": {"wall_ms": 100}
        }

        with patch('httpx.Client') as mock_client_class:
            with patch('uuid.uuid4', return_value="generated-uuid"):
                mock_client = MagicMock()
                mock_client_class.return_value.__enter__.return_value = mock_client
                mock_client.post.return_value = mock_response

                response = client.run(
                    code="x = 1",
                    variables={},
                    schema={}
                )

                call_args = mock_client.post.call_args
                request_body = call_args[1]["json"]
                assert request_body["job_id"] == "generated-uuid"

    def test_run_default_timeout_and_memory(self):
        """Test run uses default timeout and memory"""
        client = PyRunnerClient(base_url="http://test:8080/run")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "job_id": "test",
            "status": "OK",
            "variables": None,
            "added_variables": {},
            "removed_variables": [],
            "logs": {"stdout": "", "stderr": ""},
            "metrics": {"wall_ms": 100}
        }

        with patch('httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            client.run(
                code="x = 1",
                variables={},
                schema={}
            )

            call_args = mock_client.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["timeout_seconds"] == 8
            assert request_body["memory_mb"] == 256

    def test_run_custom_timeout_and_memory(self):
        """Test run uses custom timeout and memory"""
        client = PyRunnerClient(base_url="http://test:8080/run")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "job_id": "test",
            "status": "OK",
            "variables": None,
            "added_variables": {},
            "removed_variables": [],
            "logs": {"stdout": "", "stderr": ""},
            "metrics": {"wall_ms": 100}
        }

        with patch('httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            client.run(
                code="x = 1",
                variables={},
                schema={},
                timeout_seconds=15,
                memory_mb=512
            )

            call_args = mock_client.post.call_args
            request_body = call_args[1]["json"]
            assert request_body["timeout_seconds"] == 15
            assert request_body["memory_mb"] == 512
