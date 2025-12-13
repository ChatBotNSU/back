from models.execution_state import RunTimeExecutionState
from models.nodes import FileAnswer
from models.chatbot import Chatbot

from .FailExecutor import FailExecutor

class FileAnswerExecutor():
    async def execute(self, execution_state: RunTimeExecutionState, node: FileAnswer, chatbot: Chatbot):
        
        variable_type = ""
        for variable in chatbot.variables:
            if variable.name == node.assigned_variable:
                variable_type = variable.type
        

        if variable_type == "":
            FailExecutor().execute(execution_state, "Set variable executor: variable not found")
            return
        
        if variable_type == "number":
            FailExecutor().execute(execution_state, "Set variable executor: variable type mismatch. Variable is number")
            return
        
        if execution_state.in_message.files and len(execution_state.in_message.files) != 0:
            execution_state.variable_values[node.assigned_variable] = execution_state.in_message.files[0]
        elif execution_state.in_message.audios and len(execution_state.in_message.audios) != 0:
            execution_state.variable_values[node.assigned_variable] = execution_state.in_message.audios[0]
        elif execution_state.in_message.images and len(execution_state.in_message.images) != 0:
            execution_state.variable_values[node.assigned_variable] = execution_state.in_message.images[0]
        else:
            FailExecutor().execute(execution_state, "Set variable executor: in message doesnt contain any file path")
            return

        execution_state.executing_node_id = node.next_node_id
