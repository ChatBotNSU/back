from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
import uuid


class SessionState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"
    DONE = "done"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = "default"
    project_id: str = ""
    flow_id: str
    bot_id: str = ""
    channel: str = ""
    user_id: str = ""

    state: SessionState = SessionState.IDLE
    current_node: str | None = None

    variables: dict[str, Any] = Field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Stack for subgraph return addresses
    call_stack: list[str] = Field(default_factory=list)

    steps_count: int = 0
    max_steps: int = 100

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    error: str | None = None

    def touch(self) -> None:
        self.updated_at = _now()
