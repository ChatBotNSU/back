from __future__ import annotations

from typing import Any, Awaitable, Callable

from models.flow import Flow

FlowLoader = Callable[[str], Awaitable[Flow | None]]


def make_flow_loader(flow_store: Any) -> FlowLoader:
    """
    Build a flow_loader for the runner that understands subgraph version pins.

    A reference of the form ``flow_id@version`` loads the immutable snapshot of
    that version; a bare ``flow_id`` loads the current/latest flow.
    """

    async def loader(ref: str) -> Flow | None:
        if "@" in ref:
            flow_id, _, raw_version = ref.rpartition("@")
            try:
                return await flow_store.get_version(flow_id, int(raw_version))
            except ValueError:
                # "@" was part of the id, not a version pin.
                return await flow_store.get(ref)
        return await flow_store.get(ref)

    return loader
