"""Tests for flow versioning + subgraph version pinning."""
from __future__ import annotations

from engine.loader import make_flow_loader
from engine.registry import load_all_handlers
from engine.runner import start_flow
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from models.session import Session
from stores.flow_store import InMemoryFlowStore

load_all_handlers()


def _child(text: str) -> Flow:
    return Flow(
        id="child",
        start_node="c1",
        nodes={
            "c1": Node(id="c1", type=NodeType.SEND_MESSAGE,
                       config={"text": text}, exec_out=ExecOut(fallback="cend")),
            "cend": Node(id="cend", type=NodeType.END),
        },
    )


def _parent(flow_version=None) -> Flow:
    cfg = {"flow_id": "child"}
    if flow_version is not None:
        cfg["flow_version"] = flow_version
    return Flow(
        id="parent",
        start_node="s1",
        nodes={
            "s1": Node(id="s1", type=NodeType.SUBGRAPH, config=cfg,
                       exec_out=ExecOut(fallback="pend")),
            "pend": Node(id="pend", type=NodeType.END),
        },
    )


class TestFlowStoreVersioning:
    async def test_plain_save_does_not_snapshot(self):
        store = InMemoryFlowStore()
        flow = _child("draft")
        await store.save(flow)
        # No version is committed until create_version is called.
        assert flow.version == 0
        assert await store.get_version("child", 1) is None

    async def test_create_version_snapshots(self):
        store = InMemoryFlowStore()
        await store.save(_child("v1-text"))
        await store.create_version("child")
        await store.save(_child("v2-text"))
        await store.create_version("child")
        latest = await store.get("child")
        assert latest.version == 2

        v1 = await store.get_version("child", 1)
        v2 = await store.get_version("child", 2)
        assert v1.nodes["c1"].config["text"] == "v1-text"
        assert v2.nodes["c1"].config["text"] == "v2-text"

    async def test_create_version_unknown_flow(self):
        store = InMemoryFlowStore()
        assert await store.create_version("ghost") is None

    async def test_get_version_missing(self):
        store = InMemoryFlowStore()
        await store.save(_child("x"))
        await store.create_version("child")
        assert await store.get_version("child", 99) is None

    async def test_delete_removes_versions(self):
        store = InMemoryFlowStore()
        await store.save(_child("x"))
        await store.create_version("child")
        await store.delete("child")
        assert await store.get_version("child", 1) is None


class TestSubgraphPinning:
    async def test_pinned_version_runs_old_definition(self):
        store = InMemoryFlowStore()
        await store.save(_child("child-v1"))
        await store.create_version("child")  # version 1
        await store.save(_child("child-v2"))
        await store.create_version("child")  # version 2 (latest)

        parent = _parent(flow_version=1)
        loader = make_flow_loader(store)
        session = await start_flow(Session(flow_id="parent"), parent, flow_loader=loader)

        # Pinned to v1 → must execute the old text even though latest is v2.
        assert session.node_outputs["c1"]["message"]["text"] == "child-v1"

    async def test_unpinned_runs_latest(self):
        store = InMemoryFlowStore()
        await store.save(_child("child-v1"))
        await store.create_version("child")
        await store.save(_child("child-v2"))
        await store.create_version("child")

        parent = _parent(flow_version=None)
        loader = make_flow_loader(store)
        session = await start_flow(Session(flow_id="parent"), parent, flow_loader=loader)

        assert session.node_outputs["c1"]["message"]["text"] == "child-v2"
