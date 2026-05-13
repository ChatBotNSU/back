import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from engine.engine import Engine, node_executors
from engine.engine_factory import EngineFactory
from models.execution_state import ExecutionState, InMessage, OutMessage, RunTimeExecutionState
from models.chatbot import Chatbot, Variable, Graph
from models.nodes import TextAnswer, SendMessage


class TestEngine:
    """Tests for Engine class"""

    @pytest.mark.asyncio
    async def test_execute_text_answer_node(self):
        """Test executing text_answer node"""
        chatbot = Chatbot(
            bot_id=1,
            bot_name="Test",
            variables=[Variable(name="user_name", type="string")],
            graph=Graph(
                root="node_1",
                nodes={
                    "node_1": TextAnswer(assigned_variable="user_name", next_node_id="node_2"),
                    "node_2": SendMessage(next_node_id="node_3")
                }
            )
        )

        execution_state = ExecutionState(
            bot_id=1,
            execution_id=1,
            executing_node_id="node_1",
            variable_values={"user_name": ""}
        )

        engine = Engine(chatbot, execution_state)

        message = InMessage(text="John", images=[], audios=[], files=[])

        # Mock the text_answer executor
        original_executor = node_executors["text_answer"]
        mock_executor = AsyncMock()
        
        async def mock_execute(state, node, bot):
            state.variable_values["user_name"] = "John"
            state.executing_node_id = "node_2"
        
        mock_executor.execute = mock_execute
        
        with patch.dict('engine.engine.node_executors', {"text_answer": mock_executor}, clear=False):
            with patch.object(engine, 'runtime_execution_state', None, create=True):
                result = await engine.execute(message)

                assert engine.runtime_execution_state.variable_values["user_name"] == "John"

    @pytest.mark.asyncio
    async def test_execute_unknown_node_type(self):
        """Test executing unknown node type"""
        # Create a chatbot with a node that has an unknown type
        chatbot = Chatbot(
            bot_id=1,
            bot_name="Test",
            variables=[],
            graph=Graph(
                root="node_1",
                nodes={}
            )
        )
        # Add unknown node directly to graph
        chatbot.graph.nodes["node_1"] = MagicMock()
        chatbot.graph.nodes["node_1"].type = "unknown_type"

        execution_state = ExecutionState(
            bot_id=1,
            execution_id=1,
            executing_node_id="node_1",
            variable_values={}
        )

        engine = Engine(chatbot, execution_state)

        message = InMessage(text="test", images=[], audios=[], files=[])

        result = await engine.execute(message)

        assert "DEVELOPER IS AN IDIOT" in result.text
        assert "Node executor not found" in result.text

    @pytest.mark.asyncio
    async def test_execute_send_message_node(self):
        """Test executing send_message node stops loop"""
        chatbot = Chatbot(
            bot_id=1,
            bot_name="Test",
            variables=[],
            graph=Graph(
                root="node_1",
                nodes={
                    "node_1": SendMessage(next_node_id="node_2")
                }
            )
        )

        execution_state = ExecutionState(
            bot_id=1,
            execution_id=1,
            executing_node_id="node_1",
            variable_values={}
        )

        engine = Engine(chatbot, execution_state)

        message = InMessage(text="test", images=[], audios=[], files=[])

        # Mock the send_message executor to set the flag
        original_executor = node_executors["send_message"]
        mock_executor = AsyncMock()
        
        async def mock_execute(state, node, bot):
            state.send_message_flag = True
        
        mock_executor.execute = mock_execute
        
        with patch.dict('engine.engine.node_executors', {"send_message": mock_executor}, clear=False):
            result = await engine.execute(message)

            assert engine.runtime_execution_state.send_message_flag == True


class TestEngineFactory:
    """Tests for EngineFactory class"""

    def test_singleton_pattern(self):
        """Test EngineFactory is singleton"""
        factory1 = EngineFactory()
        factory2 = EngineFactory()

        assert factory1 is factory2

    @patch('minio_controller.S3Client.Minio')
    def test_get_engine_creates_new(self, mock_minio_class):
        """Test get_engine creates new engine"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        # Reset singletons
        from minio_controller.S3Client import S3Client
        S3Client._instance = None
        EngineFactory.existing_engines = {}

        # Create S3Client instance
        S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        # Mock download_chatbot
        chatbot = Chatbot(
            bot_id=1,
            bot_name="Test",
            variables=[Variable(name="test_var", type="string")],
            graph=Graph(root="node_1", nodes={})
        )

        with patch.object(S3Client, 'download_chatbot', return_value=chatbot):
            factory = EngineFactory()
            engine = factory.get_engine(execution_id=100, chatbot_id=1)

            assert isinstance(engine, Engine)
            assert engine.chatbot.bot_id == 1
            assert 100 in EngineFactory.existing_engines

    @patch('minio_controller.S3Client.Minio')
    def test_get_engine_returns_cached(self, mock_minio_class):
        """Test get_engine returns cached engine"""
        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_minio

        # Reset singletons
        from minio_controller.S3Client import S3Client
        S3Client._instance = None
        EngineFactory.existing_engines = {}

        # Create S3Client instance
        S3Client(
            endpoint="localhost:9000",
            access_key="test-user",
            secret_key="test-password"
        )

        chatbot = Chatbot(
            bot_id=1,
            bot_name="Test",
            variables=[Variable(name="test_var", type="string")],
            graph=Graph(root="node_1", nodes={})
        )

        with patch.object(S3Client, 'download_chatbot', return_value=chatbot):
            factory = EngineFactory()
            engine1 = factory.get_engine(execution_id=100, chatbot_id=1)
            engine2 = factory.get_engine(execution_id=100, chatbot_id=1)

            assert engine1 is engine2
