"""
Tests for SQLFlowStore (via SQLite/aiosqlite).
"""
import pytest

from models.flow import Flow
from models.node import Node, NodeType, ExecOut, ExecCondition
from stores.flow_store import SQLFlowStore


@pytest.fixture()
def store(db_session_factory):
    return SQLFlowStore(db_session_factory)


def _flow(name: str = "Test flow") -> Flow:
    n1 = Node(
        id="n1",
        type=NodeType.SEND_MESSAGE,
        config={"text": "Hello"},
        exec_out=ExecOut(fallback="n2"),
    )
    n2 = Node(id="n2", type=NodeType.END)
    return Flow(name=name, nodes={"n1": n1, "n2": n2}, start_node="n1")


class TestSQLFlowStore:
    async def test_save_and_get(self, store):
        flow = _flow("My flow")
        await store.save(flow)
        got = await store.get(flow.id)
        assert got is not None
        assert got.id == flow.id
        assert got.name == "My flow"

    async def test_get_missing_returns_none(self, store):
        assert await store.get("no-such-id") is None

    async def test_nodes_survive_round_trip(self, store):
        flow = _flow()
        await store.save(flow)
        got = await store.get(flow.id)
        assert "n1" in got.nodes
        assert "n2" in got.nodes
        assert got.nodes["n1"].type == NodeType.SEND_MESSAGE
        assert got.nodes["n1"].config["text"] == "Hello"
        assert got.nodes["n1"].exec_out.fallback == "n2"

    async def test_exec_out_conditions_round_trip(self, store):
        cond = ExecCondition(**{"if": "$data.ok", "eq": True, "goto": "n2"})
        n1 = Node(
            id="n1",
            type=NodeType.HTTP_CALL,
            exec_out=ExecOut(conditions=[cond], fallback="n_err"),
        )
        flow = Flow(name="cond flow", nodes={"n1": n1}, start_node="n1")
        await store.save(flow)
        got = await store.get(flow.id)
        assert len(got.nodes["n1"].exec_out.conditions) == 1
        c = got.nodes["n1"].exec_out.conditions[0]
        assert c.if_ == "$data.ok"
        assert c.eq is True
        assert c.goto == "n2"
        assert got.nodes["n1"].exec_out.fallback == "n_err"

    async def test_update_existing_flow(self, store):
        flow = _flow("Original")
        await store.save(flow)
        flow.name = "Updated"
        await store.save(flow)
        got = await store.get(flow.id)
        assert got.name == "Updated"

    async def test_delete(self, store):
        flow = _flow()
        await store.save(flow)
        await store.delete(flow.id)
        assert await store.get(flow.id) is None

    async def test_delete_nonexistent_noop(self, store):
        await store.delete("ghost")  # should not raise

    async def test_list_all(self, store):
        f1 = _flow("A")
        f2 = _flow("B")
        await store.save(f1)
        await store.save(f2)
        flows = await store.list_all()
        ids = {f.id for f in flows}
        assert f1.id in ids
        assert f2.id in ids

    async def test_list_all_limit(self, store):
        for i in range(5):
            await store.save(_flow(f"flow-{i}"))
        result = await store.list_all(limit=3)
        assert len(result) == 3

    async def test_start_node_preserved(self, store):
        flow = _flow()
        flow.start_node = "n2"
        await store.save(flow)
        got = await store.get(flow.id)
        assert got.start_node == "n2"

    async def test_metadata_round_trip(self, store):
        flow = _flow()
        flow.metadata = {"channel": "telegram", "version": 2}
        await store.save(flow)
        got = await store.get(flow.id)
        assert got.metadata["channel"] == "telegram"
        assert got.metadata["version"] == 2

    async def test_empty_flow_no_nodes(self, store):
        flow = Flow(name="empty")
        await store.save(flow)
        got = await store.get(flow.id)
        assert got.nodes == {}
        assert got.start_node is None
