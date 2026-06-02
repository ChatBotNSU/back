from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    # Triggers
    MESSAGE_TRIGGER = "message_trigger"
    WEBHOOK_TRIGGER = "webhook_trigger"
    CRON_TRIGGER = "cron_trigger"
    # Messages
    SEND_MESSAGE = "send_message"
    USER_INPUT = "user_input"
    # Logic & AI
    INTENT = "intent"
    SLOT_FILL = "slot_fill"
    AI = "ai"
    # Data
    TRANSFORM = "transform"
    LOOP = "loop"
    # Integrations
    HTTP_CALL = "http_call"
    CRM = "crm"
    NOTIFY = "notify"
    SHEETS = "sheets"
    CALENDAR = "calendar"
    PAYMENT = "payment"
    # Flow control
    WAIT = "wait"
    HANDOFF = "handoff"
    SUBGRAPH = "subgraph"
    END = "end"
    # Advanced
    CODE = "code"
    DATABASE = "database"
    SQL = "sql"


class ExecCondition(BaseModel):
    if_: str = Field(alias="if")
    eq: Any = None
    neq: Any = None
    gt: Any = None
    lt: Any = None
    contains: Any = None
    exists: bool | None = None
    not_exists: bool | None = None
    in_: list[Any] | None = Field(default=None, alias="in")
    goto: str

    model_config = {"populate_by_name": True}


class ExecOut(BaseModel):
    conditions: list[ExecCondition] = Field(default_factory=list)
    fallback: str | None = None


class DataInPort(BaseModel):
    type: str = "any"
    from_: str | None = Field(default=None, alias="from")

    model_config = {"populate_by_name": True}


class NodePosition(BaseModel):
    x: float = 0
    y: float = 0


class Node(BaseModel):
    id: str
    type: NodeType
    label: str = ""
    data_in: dict[str, DataInPort] = Field(default_factory=dict)
    data_out: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    exec_out: ExecOut = Field(default_factory=ExecOut)
    position: NodePosition = Field(default_factory=NodePosition)
