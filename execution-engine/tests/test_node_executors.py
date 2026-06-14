import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from models.execution_state import RunTimeExecutionState, InMessage, OutMessage, Frame
from models.chatbot import Chatbot, Graph
from models.nodes import TextAnswer, SetMessage, SetVariable, SendMessage, ConditionNode, ScriptExecution, Wait, FileAnswer, Condition, Branch

from engine.nodes.TextAnswerExecutor import TextAnswerExecutor
from engine.nodes.SetMessageExecutor import SetMessageExecutor
from engine.nodes.SetVariableExecutor import SetVariableExecutor
from engine.nodes.SendMessageExecutor import SendMessageExecutor
from engine.nodes.ConditionNodeExecutor import ConditionNodeExecutor
from engine.nodes.FailExecutor import FailExecutor
from engine.nodes.FileAnswerExecutor import FileAnswerExecutor
from engine.nodes.WaitExecutor import WaitExecutor
from engine.nodes.ScriptNodeExecutor import ScriptNodeExecutor


@pytest.fixture
def base_execution_state():
    """Base execution state fixture"""
    return RunTimeExecutionState(
        bot_id=1,
        execution_id=1,
        call_stack=[
            Frame(
                subgraph_name=None,
                executing_node_id="node_1",
                variable_values={}
            )
        ],
        in_message=InMessage(text="", images=[], audios=[], files=[]),
        out_message=OutMessage(),
        send_message_flag=False
    )


@pytest.fixture
def base_chatbot():
    """Base chatbot fixture"""
    return Chatbot(
        bot_id=1,
        bot_name="Test",
        graph=Graph(root="node_1", nodes={}),
        subgraphs={}
    )


class TestTextAnswerExecutor:
    """Tests for TextAnswerExecutor"""

    @pytest.mark.asyncio
    async def test_execute_string_variable(self, base_execution_state, base_chatbot):
        """Test executing with string variable"""
        executor = TextAnswerExecutor()

        base_execution_state.call_stack[-1].variable_values = {"user_name": ""}
        base_execution_state.in_message.text = "John"

        node = TextAnswer(assigned_variable="user_name", next_node_id="node_2")

        await executor.execute(base_execution_state, node, base_chatbot)

        assert base_execution_state.call_stack[-1].variable_values["user_name"] == "John"
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_number_variable(self, base_execution_state, base_chatbot):
        """Test executing with number variable"""
        executor = TextAnswerExecutor()

        base_execution_state.call_stack[-1].variable_values = {"user_age": 0}
        base_execution_state.in_message.text = "25"

        node = TextAnswer(assigned_variable="user_age", next_node_id="node_2")

        await executor.execute(base_execution_state, node, base_chatbot)

        assert base_execution_state.call_stack[-1].variable_values["user_age"] == "25"
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_variable_not_found(self, base_execution_state, base_chatbot):
        """Test executing when variable not found - skipped as variables are no longer validated against chatbot"""
        # This test is obsolete: TextAnswerExecutor no longer validates variables against chatbot
        # Variables are stored directly in execution_state.call_stack[-1].variable_values
        pytest.skip("Variable validation against chatbot is obsolete")

    @pytest.mark.asyncio
    async def test_execute_none_text(self, base_execution_state, base_chatbot):
        """Test executing with None text"""
        executor = TextAnswerExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"user_name": ""}
        base_execution_state.in_message.text = None
        
        
        node = TextAnswer(assigned_variable="user_name", next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert "DEVELOPER IS AN IDIOT" in base_execution_state.out_message.text


class TestSetMessageExecutor:
    """Tests for SetMessageExecutor"""

    @pytest.mark.asyncio
    async def test_execute_with_formatting(self, base_execution_state, base_chatbot):
        """Test executing with variable formatting"""
        executor = SetMessageExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"user_name": "John", "user_age": 25}
        
        node = SetMessage(
            text="Hello, {user_name}! You are {user_age} years old.",
            next_node_id="node_2",
            audios=[],
            images=[],
            files=[],
            choise_options=[]
        )
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.out_message.text == "Hello, John! You are 25 years old."
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"


class TestSetVariableExecutor:
    """Tests for SetVariableExecutor"""

    @pytest.mark.asyncio
    async def test_execute_number_addition(self, base_execution_state, base_chatbot):
        """Test executing number variable addition"""
        executor = SetVariableExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"counter": 10}
        
        
        node = SetVariable(assigned_variable="counter", operation="+=", operand=5, next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].variable_values["counter"] == 15.0
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_string_concatenation(self, base_execution_state, base_chatbot):
        """Test executing string variable concatenation"""
        executor = SetVariableExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"message": "Hello"}
        
        
        node = SetVariable(assigned_variable="message", operation="+=", operand=" World", next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].variable_values["message"] == "Hello World"
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_variable_not_found(self, base_execution_state, base_chatbot):
        """Test executing when variable not found for += operation"""
        executor = SetVariableExecutor()

        # += requires variable to exist
        node = SetVariable(assigned_variable="nonexistent", operation="+=", operand=5, next_node_id="node_2")

        await executor.execute(base_execution_state, node, base_chatbot)

        assert "DEVELOPER IS AN IDIOT" in base_execution_state.out_message.text
        assert "nonexistent" in base_execution_state.out_message.text


class TestSendMessageExecutor:
    """Tests for SendMessageExecutor"""

    @pytest.mark.asyncio
    async def test_execute_sets_flag(self, base_execution_state, base_chatbot):
        """Test executing sets send_message_flag"""
        executor = SendMessageExecutor()
        
        node = SendMessage(next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.send_message_flag == True
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"


class TestConditionNodeExecutor:
    """Tests for ConditionNodeExecutor"""

    @pytest.mark.asyncio
    async def test_execute_equal_condition_true(self, base_execution_state, base_chatbot):
        """Test executing == condition that is true"""
        executor = ConditionNodeExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"a": 5, "b": 5}
        
        
        condition = Condition(variable_left="a", variable_right="b", operation="==")
        branch = Branch(condition=condition, next_node_id="true_node")
        node = ConditionNode(branches=[branch], default_next_node_id="false_node")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].executing_node_id == "true_node"

    @pytest.mark.asyncio
    async def test_execute_greater_condition_true(self, base_execution_state, base_chatbot):
        """Test executing > condition that is true"""
        executor = ConditionNodeExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"a": 10, "b": 5}
        
        
        condition = Condition(variable_left="a", variable_right="b", operation=">")
        branch = Branch(condition=condition, next_node_id="true_node")
        node = ConditionNode(branches=[branch], default_next_node_id="false_node")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].executing_node_id == "true_node"

    @pytest.mark.asyncio
    async def test_execute_default_branch(self, base_execution_state, base_chatbot):
        """Test executing default branch when no conditions match"""
        executor = ConditionNodeExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"a": 3, "b": 5}
        
        
        condition = Condition(variable_left="a", variable_right="b", operation=">")
        branch = Branch(condition=condition, next_node_id="true_node")
        node = ConditionNode(branches=[branch], default_next_node_id="false_node")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].executing_node_id == "false_node"

    @pytest.mark.asyncio
    async def test_execute_variable_not_found(self, base_execution_state, base_chatbot):
        """Test executing when variable not found"""
        executor = ConditionNodeExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"a": 5}
        
        
        condition = Condition(variable_left="a", variable_right="nonexistent", operation="==")
        branch = Branch(condition=condition, next_node_id="true_node")
        node = ConditionNode(branches=[branch], default_next_node_id="false_node")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert "DEVELOPER IS AN IDIOT" in base_execution_state.out_message.text


class TestFailExecutor:
    """Tests for FailExecutor"""

    def test_execute_default_idiot(self, base_execution_state):
        """Test executing with default idiot type"""
        executor = FailExecutor()
        
        executor.execute(base_execution_state, "Test error")
        
        assert "DEVELOPER IS AN IDIOT" in base_execution_state.out_message.text
        assert "Test error" in base_execution_state.out_message.text
        assert base_execution_state.send_message_flag == True

    def test_execute_user_idiot(self, base_execution_state):
        """Test executing with USER idiot type"""
        executor = FailExecutor()
        
        executor.execute(base_execution_state, "Test error", "USER")
        
        assert "USER IS AN IDIOT" in base_execution_state.out_message.text
        assert base_execution_state.send_message_flag == True


class TestFileAnswerExecutor:
    """Tests for FileAnswerExecutor"""

    @pytest.mark.asyncio
    async def test_execute_with_file(self, base_execution_state, base_chatbot):
        """Test executing with file in message"""
        executor = FileAnswerExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"user_file": ""}
        base_execution_state.in_message.files = ["/path/to/file.pdf"]
        
        
        node = FileAnswer(assigned_variable="user_file", next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].variable_values["user_file"] == "/path/to/file.pdf"
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_with_audio(self, base_execution_state, base_chatbot):
        """Test executing with audio in message"""
        executor = FileAnswerExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"user_audio": ""}
        base_execution_state.in_message.audios = ["/path/to/audio.mp3"]
        
        
        node = FileAnswer(assigned_variable="user_audio", next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].variable_values["user_audio"] == "/path/to/audio.mp3"
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_with_image(self, base_execution_state, base_chatbot):
        """Test executing with image in message"""
        executor = FileAnswerExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"user_image": ""}
        base_execution_state.in_message.images = ["/path/to/image.png"]
        
        
        node = FileAnswer(assigned_variable="user_image", next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].variable_values["user_image"] == "/path/to/image.png"
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_no_files(self, base_execution_state, base_chatbot):
        """Test executing with no files in message"""
        executor = FileAnswerExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {}
        base_execution_state.in_message.files = []
        
        
        node = FileAnswer(assigned_variable="user_file", next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert "DEVELOPER IS AN IDIOT" in base_execution_state.out_message.text

    @pytest.mark.asyncio
    async def test_execute_number_variable(self, base_execution_state, base_chatbot):
        """Test executing with number variable type - skipped as FileAnswerExecutor no longer validates types"""
        # This test is obsolete: FileAnswerExecutor no longer validates variable types
        pytest.skip("Type validation for file variables is obsolete")


class TestWaitExecutor:
    """Tests for WaitExecutor"""

    @pytest.mark.asyncio
    async def test_execute_waits_and_continues(self, base_execution_state, base_chatbot):
        """Test executing waits for specified time"""
        executor = WaitExecutor()
        
        node = Wait(wait_time=1, next_node_id="node_2")
        
        await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"


class TestScriptNodeExecutor:
    """Tests for ScriptNodeExecutor"""

    @pytest.mark.asyncio
    async def test_execute_success(self, base_execution_state, base_chatbot, mock_py_runner_client):
        """Test executing script successfully"""
        executor = ScriptNodeExecutor()

        base_execution_state.call_stack[-1].variable_values = {"x": 5, "y": 10}
        

        node = ScriptExecution(script="result = x + y", next_node_id="node_2")
        
        mock_response = MagicMock()
        mock_response.status = "OK"
        mock_response.variables = {"x": 5, "y": 10, "result": 15}
        mock_response.removed_variables = []
        mock_py_runner_client.return_value.run.return_value = mock_response
        
        with patch('engine.nodes.ScriptNodeExecutor.PyRunnerClient', mock_py_runner_client):
            await executor.execute(base_execution_state, node, base_chatbot)
        
        assert base_execution_state.call_stack[-1].variable_values["result"] == 15
        assert base_execution_state.call_stack[-1].executing_node_id == "node_2"

    @pytest.mark.asyncio
    async def test_execute_runner_error(self, base_execution_state, base_chatbot, mock_py_runner_client):
        """Test executing script with runner error"""
        executor = ScriptNodeExecutor()
        
        base_execution_state.call_stack[-1].variable_values = {"x": 5}
        
        
        node = ScriptExecution(script="result = x + y", next_node_id="node_2")
        
        mock_response = MagicMock()
        mock_response.status = "RUNTIME_ERROR"
        mock_response.error = MagicMock(message="NameError: name 'y' is not defined")
        mock_py_runner_client.return_value.run.return_value = mock_response
        
        with patch('engine.nodes.ScriptNodeExecutor.PyRunnerClient', mock_py_runner_client):
            await executor.execute(base_execution_state, node, base_chatbot)
        
        assert "DEVELOPER IS AN IDIOT" in base_execution_state.out_message.text
        assert "Script executor: NameError" in base_execution_state.out_message.text

    @pytest.mark.asyncio
    async def test_execute_no_code(self, base_execution_state, base_chatbot, mock_py_runner_client):
        """Test executing script with no code"""
        executor = ScriptNodeExecutor()
        
        
        node = ScriptExecution(script="", next_node_id="node_2")
        
        with patch('engine.nodes.ScriptNodeExecutor.PyRunnerClient', mock_py_runner_client):
            await executor.execute(base_execution_state, node, base_chatbot)
        
        assert "DEVELOPER IS AN IDIOT" in base_execution_state.out_message.text
