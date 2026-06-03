from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from models.node import NodeType

if TYPE_CHECKING:
    from models.node import Node
    from models.session import Session


class Handler(Protocol):
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: "Session",
        node: "Node",
    ) -> dict[str, Any]: ...


_registry: dict[NodeType, Handler] = {}


def register(node_type: NodeType, handler: Handler) -> None:
    _registry[node_type] = handler


def get(node_type: NodeType) -> Handler:
    if node_type not in _registry:
        raise KeyError(f"No handler registered for node type: {node_type!r}")
    return _registry[node_type]


def load_all_handlers() -> None:
    """Import all handler modules so they self-register."""
    import handlers.message_trigger  # noqa: F401
    import handlers.webhook_trigger  # noqa: F401
    import handlers.cron_trigger     # noqa: F401
    import handlers.send_message     # noqa: F401
    import handlers.user_input       # noqa: F401
    import handlers.intent           # noqa: F401
    import handlers.slot_fill        # noqa: F401
    import handlers.ai               # noqa: F401
    import handlers.transform        # noqa: F401
    import handlers.loop             # noqa: F401
    import handlers.http_call        # noqa: F401
    import handlers.crm              # noqa: F401
    import handlers.notify           # noqa: F401
    import handlers.sheets           # noqa: F401
    import handlers.calendar         # noqa: F401
    import handlers.payment          # noqa: F401
    import handlers.wait             # noqa: F401
    import handlers.handoff          # noqa: F401
    import handlers.subgraph         # noqa: F401
    import handlers.code             # noqa: F401
    import handlers.database         # noqa: F401
    import handlers.sql              # noqa: F401
    import handlers.end              # noqa: F401
