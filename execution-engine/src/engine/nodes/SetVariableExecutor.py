import logging

from models.execution_state import RunTimeExecutionState
from models.chatbot import Chatbot
from models.nodes import SetVariable

from .FailExecutor import FailExecutor

logger = logging.getLogger("app")


class SetVariableExecutor():
    async def execute(self, execution_state: RunTimeExecutionState, node: SetVariable, chatbot: Chatbot):
        execution_state.executing_node_id = node.next_node_id
        logger.info("STEP 0")
        variable_type = ""
        for variable in chatbot.variables:
            if variable.name == node.assigned_variable:
                variable_type = variable.type
        
        logger.info(execution_state.variable_values)
        if variable_type == "":
            FailExecutor().execute(execution_state, "Set variable executor: variable not found")
            return


        variable_value = execution_state.variable_values[node.assigned_variable]

        logger.info("STEP 2")
        if variable_type == "number":
            try:
                variable_value = float(variable_value)
                node.operand = float(node.operand)
            except:
                FailExecutor().execute(execution_state, "Set variable executor: variable type mismatch", "USER")
                return
            
            if node.operation == "+=":
                variable_value += node.operand
            if node.operation == "=":
                variable_value += node.operand
            elif node.operation == "-=":
                variable_value -= node.operand
            elif node.operation == "/=":
                variable_value /= node.operand
            elif node.operation == "*=":
                variable_value *= node.operand
            elif node.operation == "%=":
                variable_value %= node.operand
        
        else:
            try:
                variable_value = str(variable_value)
                node.operand = str(node.operand)
            except:
                FailExecutor().execute(execution_state, "Set variable executor: variable type mismatch", "USER")
                return
            
            if node.operation == "+=":
                variable_value += node.operand

        
        logger.info("STEP 3")
        execution_state.variable_values[node.assigned_variable] = variable_value
