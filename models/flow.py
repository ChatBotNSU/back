from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field
import uuid

from .node import Node


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Flow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = "default"
    project_id: str = ""
    name: str = ""
    description: str = ""

    nodes: dict[str, Node] = Field(default_factory=dict)
    start_node: str | None = None

    # Latest committed version number. A plain save overwrites the working
    # draft without bumping it; versions are created explicitly (see
    # FlowStore.create_version). Subgraph nodes may pin to a specific version
    # via `config.flow_version` (see handlers/subgraph.py).
    version: int = 1

    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @classmethod
    def from_node_list(cls, nodes: list[Node], **kwargs: Any) -> "Flow":
        return cls(nodes={n.id: n for n in nodes}, **kwargs)
