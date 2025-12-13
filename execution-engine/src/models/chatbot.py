from pydantic import Field, BaseModel
from typing import Annotated, Union, Literal


from .nodes import SendMessage, SetMessage, SetVariable, ScriptExecution, FileAnswer, TextAnswer, Wait, ConditionNode

class Variable(BaseModel):
    name: str
    type: Literal["string", "number"]


NodeType = Annotated[
    Union[SetVariable, ScriptExecution, FileAnswer, TextAnswer, SendMessage, Wait, SetMessage, ConditionNode],
    Field(discriminator="type")
]

class Graph(BaseModel):
    root: str # root node id
    nodes: dict[str, NodeType]

class Chatbot(BaseModel):
    variables: list[Variable]
    graph: Graph
    bot_id: int
    bot_name: str
