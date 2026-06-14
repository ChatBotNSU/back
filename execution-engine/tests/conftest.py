"""Minimal pytest setup for execution-engine: make backend modules importable.

We deliberately do NOT spin up Redis or MinIO for these tests. Each test drives
`Engine.execute` directly against an in-memory Chatbot.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch
import json

from models.chatbot import Chatbot
from models.execution_state import ExecutionState, InMessage, OutMessage, Frame
from models.nodes import TextAnswer, SetMessage, SetVariable, SendMessage, ConditionNode, ScriptExecution, Wait, FileAnswer


# Insert src/ on sys.path so bare imports ('from models...', 'from engine...') work.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# Note: sandbox_runner is no longer stubbed here. Tests that need it should import directly.
# ScriptNodeExecutor tests use mock_py_runner_client fixture.

@pytest.fixture
def mock_minio_client():
    """Mock Minio client for S3Client tests"""
    with patch('minio.Minio') as mock_minio:
        mock_instance = MagicMock()
        mock_minio.return_value = mock_instance
        mock_instance.bucket_exists.return_value = True
        yield mock_instance


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    with patch('redis.asyncio.Redis') as mock_redis:
        mock_instance = MagicMock()
        mock_redis.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_py_runner_client():
    """Mock PyRunnerClient for ScriptNodeExecutor tests"""
    import sandbox_runner.client as client_mod
    mock_instance = MagicMock()
    original = client_mod.PyRunnerClient
    client_mod.PyRunnerClient = MagicMock(return_value=mock_instance)
    yield mock_instance
    client_mod.PyRunnerClient = original


@pytest.fixture
def test_chatbot():
    """Test chatbot with sample graph"""
    return Chatbot(
        graph={
            "root": "node_1",
            "nodes": {
                "node_1": {"type": "text_answer", "assigned_variable": "user_name", "next_node_id": "node_2"},
                "node_2": {"type": "set_message", "text": "Hello, {user_name}!", "next_node_id": "node_3"},
                "node_3": {"type": "send_message", "next_node_id": None},
            }
        },
        subgraphs={},
        bot_id=1,
        bot_name="Test Bot"
    )


@pytest.fixture
def test_execution_state():
    """Test execution state"""
    return ExecutionState(
        bot_id=1,
        execution_id=100,
        call_stack=[
            Frame(
                subgraph_name=None,
                executing_node_id="node_1",
                variable_values={"user_name": "", "user_age": 0, "user_message": ""}
            )
        ]
    )


@pytest.fixture
def test_in_message():
    """Test input message"""
    return InMessage(text="John", images=[], audios=[], files=[])


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config_data = {
        "redis": {
            "host": "localhost",
            "port": 6379,
            "IOStream": {
                "stream_requests": "requests",
                "stream_responses": "responses",
                "group": "test-group",
                "consumer": "test-consumer"
            }
        },
        "s3": {
            "host": "localhost",
            "port": 9000,
            "user": "test-user",
            "password": "test-password"
        },
        "services": {
            "py_runner": {
                "url": "http://localhost:8080/run",
                "timeout_seconds": 15
            }
        }
    }
    with patch('config.config.load_config', return_value=MagicMock(**config_data)):
        yield MagicMock(**config_data)
