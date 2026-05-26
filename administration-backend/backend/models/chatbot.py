from pydantic import Field, BaseModel
from typing import Annotated, Union


from .nodes import (
    SendMessage, SetMessage, SetVariable, ScriptExecution, FileAnswer,
    TextAnswer, Wait, ConditionNode, SubgraphCall, SubgraphExit,
)


NodeType = Annotated[
    Union[
        SetVariable, ScriptExecution, FileAnswer, TextAnswer, SendMessage,
        Wait, SetMessage, ConditionNode, SubgraphCall, SubgraphExit,
    ],
    Field(discriminator="type")
]


class Graph(BaseModel):
    root: str  # root node id
    nodes: dict[str, NodeType]


class Subgraph(BaseModel):
    name: str
    # Input parameter names. The caller MUST bind every one of these to a caller
    # variable. Bindings are by-reference: any modification of an input name
    # inside the subgraph is written back to the bound caller variable on
    # return. Everything else is local to the subgraph and disposed on exit.
    inputs: list[str] = []
    exits: list[str]  # named exit labels this subgraph can return through
    graph: Graph


class Chatbot(BaseModel):
    graph: Graph
    subgraphs: dict[str, Subgraph] = {}
    bot_id: int
    bot_name: str


class ChatbotUnassigned(BaseModel):
    graph: Graph
    subgraphs: dict[str, Subgraph] = {}
    bot_name: str
