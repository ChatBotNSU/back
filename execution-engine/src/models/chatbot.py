from typing import Literal
from enum import Enum
from pydantic import BaseModel

class Variable(BaseModel):
    name: str
    type: Literal["string", "number"]

class NodeType(Enum):
    answer = "answer"

class Node(BaseModel):
    node_id: int
    type: NodeType

class Graph(BaseModel):
    root: int # root node id
    nodes: dict[int, Node]

class Chatbot(BaseModel):
    variables: list[Variable]
    graph: Graph
    bot_id: int
    bot_name: str
