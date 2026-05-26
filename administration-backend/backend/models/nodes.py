from typing import Literal, Union

from pydantic import BaseModel


class Node(BaseModel):
    pass


class SetVariable(Node):
    type: Literal["set_variable"] = "set_variable"
    assigned_variable: str
    operation: Literal["=", "+=", "-=", "/=", "*=", "%="]
    operand: Union[str, float]
    next_node_id: str


class ScriptExecution(Node):
    type: Literal["script_execution"] = "script_execution"
    script: str
    next_node_id: str


class FileAnswer(Node):
    type: Literal["file_answer"] = "file_answer"
    assigned_variable: str
    next_node_id: str


class TextAnswer(Node):
    type: Literal["text_answer"] = "text_answer"
    assigned_variable: str
    next_node_id: str


class SendMessage(Node):
    type: Literal["send_message"] = "send_message"
    next_node_id: str


class Wait(Node):
    type: Literal["wait"] = "wait"
    wait_time: int
    next_node_id: str


class SetMessage(Node):
    type: Literal["set_message"] = "set_message"
    text: str
    audios: list[str]
    images: list[str]
    files: list[str]
    choise_options: list[str]
    next_node_id: str


class Condition(BaseModel):
    variable_left: str
    operation: Literal["==", "!=", "<", ">", "<=", ">="]
    variable_right: str


class Branch(BaseModel):
    condition: Condition
    next_node_id: str


class ConditionNode(Node):
    type: Literal["condition"] = "condition"
    branches: list[Branch]
    default_next_node_id: str


class SubgraphCall(Node):
    type: Literal["subgraph_call"] = "subgraph_call"
    subgraph_name: str
    # subgraph input parameter name -> caller variable name (kwargs-style).
    # Pass-by-reference: modifications to the input name inside the subgraph
    # are written back to the bound caller variable on return.
    input_bindings: dict[str, str]
    # subgraph exit label -> caller's next node id
    exit_next_nodes: dict[str, str]


class SubgraphExit(Node):
    type: Literal["subgraph_exit"] = "subgraph_exit"
    exit_label: str
