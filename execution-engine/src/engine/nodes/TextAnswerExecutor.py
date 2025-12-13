from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import TextAnswer
from .FailExecutor import FailExecutor


class TextAnswerExecutor:
    async def execute(self, execution_state: RunTimeExecutionState, node: TextAnswer, chatbot: Chatbot):
        
        variable_type = ""
        for variable in chatbot.variables:
            if variable.name == node.assigned_variable:
                variable_type = variable.type
        

        if variable_type == "":
            FailExecutor().execute(execution_state, "Set variable executor: variable not found")
            return
        
        if execution_state.in_message.text == None:
            FailExecutor().execute(execution_state, "Set variable executor: variable type mismatch. In message is None")
            return

        if variable_type == "number":
            try:
                variable_value = float(execution_state.in_message.text)
            except:
                FailExecutor().execute(execution_state, "Set variable executor: variable type mismatch")
                return
        else:
            variable_value = execution_state.in_message.text

        execution_state.variable_values[node.assigned_variable] = variable_value
        execution_state.executing_node_id = node.next_node_id
