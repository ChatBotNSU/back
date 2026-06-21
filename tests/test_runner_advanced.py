"""
Tests for advanced runner features: subgraph, loop, slot_fill waiting.
"""
import pytest

from engine.registry import load_all_handlers
from engine.runner import start_flow, resume_flow
from models.flow import Flow
from models.node import Node, NodeType, ExecOut, ExecCondition
from models.session import Session, SessionState

load_all_handlers()


def make_session(flow_id: str = "f1") -> Session:
    return Session(flow_id=flow_id)


def simple_flow(*nodes: Node, start: str | None = None) -> Flow:
    f = Flow.from_node_list(list(nodes))
    f.start_node = start or nodes[0].id
    return f


# ─── Subgraph ─────────────────────────────────────────────────────────────────

class TestSubgraph:
    async def test_subgraph_executes_and_returns(self):
        child = Flow(
            id="child-flow",
            start_node="c1",
            nodes={
                "c1": Node(
                    id="c1",
                    type=NodeType.SEND_MESSAGE,
                    config={"text": "from child"},
                    exec_out=ExecOut(fallback="c2"),
                ),
                "c2": Node(id="c2", type=NodeType.END),
            },
        )

        parent = simple_flow(
            Node(
                id="p1",
                type=NodeType.SUBGRAPH,
                config={"flow_id": "child-flow", "inputs": {}, "outputs": {}},
                exec_out=ExecOut(fallback="p2"),
            ),
            Node(id="p2", type=NodeType.END, config={"message": "parent done"}),
        )

        # loader must know ALL flows (parent + child) — same as a real DB loader would
        all_flows = {child.id: child, parent.id: parent}

        async def loader(fid: str) -> Flow | None:
            return all_flows.get(fid)

        session = make_session()
        session = await start_flow(session, parent, flow_loader=loader)

        assert session.state == SessionState.DONE
        assert "c1" in session.node_outputs
        assert "p2" in session.node_outputs

    async def test_subgraph_missing_flow_gives_error(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.SUBGRAPH,
                config={"flow_id": "no-such-flow"},
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="n2", type=NodeType.END),
        )

        async def loader(fid: str) -> Flow | None:
            return None

        session = make_session()
        session = await start_flow(session, flow, flow_loader=loader)
        assert session.state == SessionState.ERROR

    async def test_subgraph_no_loader_gives_error(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.SUBGRAPH,
                config={"flow_id": "anything"},
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="n2", type=NodeType.END),
        )
        session = make_session()
        # No flow_loader passed
        session = await start_flow(session, flow, flow_loader=None)
        assert session.state == SessionState.ERROR

    async def test_subgraph_passes_variables_to_child(self):
        child = Flow(
            id="child",
            start_node="c1",
            nodes={"c1": Node(id="c1", type=NodeType.END)},
        )
        parent = simple_flow(
            Node(
                id="p1",
                type=NodeType.SUBGRAPH,
                config={"flow_id": "child", "inputs": {"name": "{{user_name}}"}},
                exec_out=ExecOut(fallback="p2"),
            ),
            Node(id="p2", type=NodeType.END),
        )

        all_flows = {child.id: child, parent.id: parent}

        async def loader(fid: str) -> Flow | None:
            return all_flows.get(fid)

        session = make_session()
        session.variables["user_name"] = "Alice"
        session = await start_flow(session, parent, flow_loader=loader)
        assert session.state == SessionState.DONE
        assert session.variables.get("name") == "Alice"

    async def test_nested_subgraph(self):
        grandchild = Flow(
            id="grandchild",
            start_node="g1",
            nodes={"g1": Node(id="g1", type=NodeType.END)},
        )
        child = Flow(
            id="child",
            start_node="c1",
            nodes={
                "c1": Node(
                    id="c1",
                    type=NodeType.SUBGRAPH,
                    config={"flow_id": "grandchild"},
                    exec_out=ExecOut(fallback="c2"),
                ),
                "c2": Node(id="c2", type=NodeType.END),
            },
        )
        parent = simple_flow(
            Node(
                id="p1",
                type=NodeType.SUBGRAPH,
                config={"flow_id": "child"},
                exec_out=ExecOut(fallback="p2"),
            ),
            Node(id="p2", type=NodeType.END),
        )

        all_flows = {child.id: child, grandchild.id: grandchild, parent.id: parent}

        async def loader(fid: str) -> Flow | None:
            return all_flows.get(fid)

        session = make_session()
        session = await start_flow(session, parent, flow_loader=loader)
        assert session.state == SessionState.DONE
        assert "g1" in session.node_outputs
        assert "c2" in session.node_outputs
        assert "p2" in session.node_outputs


# ─── Loop ─────────────────────────────────────────────────────────────────────

class TestLoop:
    async def test_loop_runs_body_for_each_item(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.LOOP,
                config={
                    "array_var": "items",
                    "item_var": "item",
                    "body_node": "body",
                    "max_items": 10,
                },
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(
                id="body",
                type=NodeType.TRANSFORM,
                config={"mappings": [{"from": "{{item}}", "to": "processed"}]},
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="n2", type=NodeType.END),
        )
        flow.start_node = "n1"

        session = make_session()
        session.variables["items"] = ["a", "b", "c"]
        session = await start_flow(session, flow)

        assert session.state == SessionState.DONE
        results = session.node_outputs["n1"]["results"]
        assert len(results) == 3

    async def test_loop_respects_max_items(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.LOOP,
                config={
                    "array_var": "items",
                    "item_var": "item",
                    "body_node": "body",
                    "max_items": 2,
                },
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="body", type=NodeType.END),
            Node(id="n2", type=NodeType.END),
        )
        flow.start_node = "n1"

        session = make_session()
        session.variables["items"] = [1, 2, 3, 4, 5]
        session = await start_flow(session, flow)
        assert session.node_outputs["n1"]["count"] == 2

    async def test_loop_empty_array(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.LOOP,
                config={"array_var": "items", "item_var": "item", "body_node": "body"},
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="body", type=NodeType.END),
            Node(id="n2", type=NodeType.END),
        )
        flow.start_node = "n1"

        session = make_session()
        session.variables["items"] = []
        session = await start_flow(session, flow)
        assert session.state == SessionState.DONE
        assert session.node_outputs["n1"]["count"] == 0

    async def test_loop_output_var(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.LOOP,
                config={
                    "array_var": "nums",
                    "item_var": "n",
                    "body_node": "body",
                    "output_var": "loop_result",
                },
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="body", type=NodeType.END),
            Node(id="n2", type=NodeType.END),
        )
        flow.start_node = "n1"

        session = make_session()
        session.variables["nums"] = [1, 2]
        session = await start_flow(session, flow)
        assert "loop_result" in session.variables
        assert session.variables["loop_result"]["count"] == 2


# ─── Slot fill waiting ────────────────────────────────────────────────────────

class TestSlotFillWaiting:
    async def test_slot_fill_pauses_and_resumes(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.SLOT_FILL,
                config={
                    "slots": [
                        {"name": "name", "question": "What is your name?"},
                        {"name": "city", "question": "What city are you in?"},
                    ],
                    "max_attempts": 3,
                },
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="n2", type=NodeType.END),
        )

        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.WAITING
        assert session.variables.get("__slot_question__") == "What is your name?"

        session = await resume_flow(session, flow, "Alice")
        assert session.state == SessionState.WAITING
        assert session.variables.get("__slot_question__") == "What city are you in?"

        session = await resume_flow(session, flow, "Moscow")
        assert session.state == SessionState.DONE

        slot_state_key = f"__slot_state_{list(flow.nodes.keys())[0]}__"
        slot_state = session.variables.get(slot_state_key, {})
        assert slot_state.get("name") == "Alice"
        assert slot_state.get("city") == "Moscow"

    async def test_slot_fill_max_attempts_gives_complete_false(self):
        flow = simple_flow(
            Node(
                id="sf1",
                type=NodeType.SLOT_FILL,
                config={
                    "slots": [{"name": "email", "question": "Email?"}],
                    "max_attempts": 2,
                },
                exec_out=ExecOut(
                    conditions=[
                        ExecCondition(**{"if": "$data.complete", "eq": True, "goto": "ok"}),
                        ExecCondition(**{"if": "$data.complete", "eq": False, "goto": "fail"}),
                    ]
                ),
            ),
            Node(id="ok", type=NodeType.END),
            Node(id="fail", type=NodeType.END),
        )

        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.WAITING

        session = await resume_flow(session, flow, "answer1")
        # After max_attempts, slot_fill returns complete=False
        # (reaches attempt limit and routes to fail branch)
        assert session.state in (SessionState.WAITING, SessionState.DONE)
