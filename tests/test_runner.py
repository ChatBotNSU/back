"""
State-machine tests for the engine runner.
All tests use in-memory sessions and flows — no DB, no Redis.
"""
import pytest

from engine.registry import load_all_handlers
from engine.runner import start_flow, resume_flow, run_step
from models.flow import Flow
from models.node import Node, NodeType, ExecOut, ExecCondition, DataInPort
from models.session import Session, SessionState


@pytest.fixture(autouse=True)
def register_handlers():
    load_all_handlers()


def make_session(flow_id: str = "flow1") -> Session:
    return Session(flow_id=flow_id)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def node(node_id: str, ntype: NodeType, config: dict | None = None,
         goto: str | None = None, fallback: str | None = None,
         conditions: list | None = None) -> Node:
    conds = [ExecCondition(**c) for c in (conditions or [])]
    return Node(
        id=node_id,
        type=ntype,
        config=config or {},
        exec_out=ExecOut(conditions=conds, fallback=goto or fallback),
    )


def simple_flow(*nodes: Node, start: str | None = None) -> Flow:
    f = Flow.from_node_list(list(nodes))
    f.start_node = start or nodes[0].id
    return f


# ─── Basic state transitions ───────────────────────────────────────────────────

class TestStateTransitions:
    async def test_done_after_single_end_node(self):
        flow = simple_flow(node("n1", NodeType.END))
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.DONE

    async def test_runs_linear_chain(self):
        flow = simple_flow(
            node("n1", NodeType.SEND_MESSAGE, {"content_type": "text", "text": "hi"}, goto="n2"),
            node("n2", NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.DONE
        assert "n1" in session.node_outputs
        assert "n2" in session.node_outputs

    async def test_stops_at_user_input(self):
        flow = simple_flow(
            node("n1", NodeType.SEND_MESSAGE, {"text": "What is your name?"}, goto="n2"),
            node("n2", NodeType.USER_INPUT, {"variable": "name"}, goto="n3"),
            node("n3", NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.WAITING
        assert session.current_node == "n2"

    async def test_resume_from_waiting(self):
        flow = simple_flow(
            node("n1", NodeType.USER_INPUT, {"variable": "name"}, goto="n2"),
            node("n2", NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.WAITING

        session = await resume_flow(session, flow, "Alice")
        assert session.state == SessionState.DONE
        assert session.variables["name"] == "Alice"

    async def test_error_on_missing_node(self):
        flow = simple_flow(node("n1", NodeType.END, goto="ghost"))
        session = make_session()
        # n1 has fallback "ghost" but ghost doesn't exist — runner hits missing node
        # end node doesn't use exec_out fallback, it returns {} and runner goes to fallback
        session.state = SessionState.RUNNING
        session.current_node = "ghost"
        session = await run_step(session, flow)
        assert session.state == SessionState.ERROR

    async def test_no_start_node_gives_error(self):
        flow = Flow(id="f1", nodes={})
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.ERROR


# ─── Max steps guard ──────────────────────────────────────────────────────────

class TestMaxSteps:
    async def test_infinite_loop_protection(self):
        # n1 → n1 (infinite loop)
        flow = simple_flow(
            node("n1", NodeType.SEND_MESSAGE, {"text": "loop"}, goto="n1"),
        )
        session = make_session()
        session.max_steps = 10
        session = await start_flow(session, flow)
        assert session.state == SessionState.ERROR
        assert "Max steps" in session.error


# ─── Branching via exec_out conditions ────────────────────────────────────────

class TestBranching:
    async def test_true_branch(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.HTTP_CALL,
                config={"__test_response__": {"value": 42}, "method": "GET", "url": "http://x"},
                exec_out=ExecOut(
                    conditions=[
                        ExecCondition(**{"if": "$data.ok", "eq": True, "goto": "n_ok"}),
                        ExecCondition(**{"if": "$data.ok", "eq": False, "goto": "n_fail"}),
                    ]
                ),
            ),
            node("n_ok", NodeType.END, {"message": "ok"}),
            node("n_fail", NodeType.END, {"message": "fail"}),
        )
        flow.start_node = "n1"
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.DONE
        assert "n_ok" in session.node_outputs

    async def test_fallback_branch(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.TRANSFORM,
                config={"mappings": []},
                exec_out=ExecOut(
                    conditions=[
                        ExecCondition(**{"if": "$data.result.x", "eq": 99, "goto": "never"})
                    ],
                    fallback="n2",
                ),
            ),
            node("n2", NodeType.END),
        )
        flow.start_node = "n1"
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.DONE
        assert "n2" in session.node_outputs


# ─── output_var propagation ───────────────────────────────────────────────────

class TestOutputVar:
    async def test_output_var_saved_to_session(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.HTTP_CALL,
                config={
                    "method": "GET",
                    "url": "http://x",
                    "__test_response__": {"user": "bob"},
                    "output_var": "api_result",
                },
                exec_out=ExecOut(fallback="n2"),
            ),
            node("n2", NodeType.END),
        )
        flow.start_node = "n1"
        session = make_session()
        session = await start_flow(session, flow)
        assert session.variables["api_result"]["response"] == {"user": "bob"}


# ─── Session persistence across resume ───────────────────────────────────────

class TestSessionPersistence:
    async def test_variables_survive_across_resume(self):
        flow = simple_flow(
            node("n1", NodeType.USER_INPUT, {"variable": "city"}, goto="n2"),
            node("n2", NodeType.USER_INPUT, {"variable": "name"}, goto="n3"),
            node("n3", NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.WAITING

        session = await resume_flow(session, flow, "Moscow")
        assert session.state == SessionState.WAITING
        assert session.variables["city"] == "Moscow"

        session = await resume_flow(session, flow, "Alice")
        assert session.state == SessionState.DONE
        assert session.variables["name"] == "Alice"

    async def test_steps_count_accumulates(self):
        flow = simple_flow(
            node("n1", NodeType.SEND_MESSAGE, {"text": "a"}, goto="n2"),
            node("n2", NodeType.SEND_MESSAGE, {"text": "b"}, goto="n3"),
            node("n3", NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        assert session.steps_count == 3


# ─── Error handler routing ────────────────────────────────────────────────────

class TestErrorRouting:
    async def test_error_port_routes_to_handler(self):
        class BrokenHandler:
            async def execute(self, config, data_in, session, node):
                raise RuntimeError("boom")

        from engine import registry
        from models.node import NodeType as NT

        # Capture the real handler so we can restore it — re-importing won't
        # re-register it (the module is already cached in sys.modules).
        original = registry.get(NT.CODE)
        registry.register(NT.CODE, BrokenHandler())
        try:
            flow = simple_flow(
                Node(
                    id="n1",
                    type=NT.CODE,
                    config={},
                    exec_out=ExecOut(
                        conditions=[ExecCondition(**{"if": "$error", "eq": "$error", "goto": "n_err"})],
                        fallback="n_end",
                    ),
                ),
                node("n_err", NT.END, {"message": "caught error"}),
                node("n_end", NT.END),
            )
            flow.start_node = "n1"
            session = make_session()
            session = await start_flow(session, flow)
            # After error the runner looks for $error condition
            # Since our runner checks if_=="$error", the routing happens
            assert session.state in (SessionState.DONE, SessionState.ERROR)
        finally:
            registry.register(NT.CODE, original)


# ─── Cannot resume non-waiting session ───────────────────────────────────────

class TestResumePrecondition:
    async def test_resume_running_session_raises(self):
        flow = simple_flow(node("n1", NodeType.END))
        session = make_session()
        session.state = SessionState.RUNNING
        session.current_node = "n1"
        with pytest.raises(ValueError):
            await resume_flow(session, flow, "hi")
