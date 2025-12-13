from typing import Literal
from pydantic import BaseModel

class Variable(BaseModel):
    name: str
    type: Literal["string", "number"]

class Node(BaseModel):
    node_id: str

class Graph(BaseModel):
    root: str # root node id
    nodes: dict[str, Node]

class Chatbot(BaseModel):
    variables: list[Variable]
    graph: Graph
    bot_id: int
    bot_name: str
