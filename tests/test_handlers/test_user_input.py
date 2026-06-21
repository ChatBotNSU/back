import pytest

from engine.registry import load_all_handlers
from engine.runner import start_flow, resume_flow
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from models.session import Session, SessionState

load_all_handlers()


def make_session() -> Session:
    return Session(flow_id="f1")


def simple_flow(*nodes: Node) -> Flow:
    f = Flow.from_node_list(list(nodes))
    f.start_node = nodes[0].id
    return f


class TestUserInput:
    async def test_pauses_on_first_call(self):
        flow = simple_flow(
            Node(id="n1", type=NodeType.USER_INPUT, config={"variable": "answer"}, exec_out=ExecOut(fallback="n2")),
            Node(id="n2", type=NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        assert session.state == SessionState.WAITING
        assert session.current_node == "n1"

    async def test_resumes_and_stores_variable(self):
        flow = simple_flow(
            Node(id="n1", type=NodeType.USER_INPUT, config={"variable": "color"}, exec_out=ExecOut(fallback="n2")),
            Node(id="n2", type=NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        session = await resume_flow(session, flow, "blue")
        assert session.state == SessionState.DONE
        assert session.variables["color"] == "blue"

    async def test_number_type_coercion(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.USER_INPUT,
                config={"variable": "age", "input_type": "number"},
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="n2", type=NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        session = await resume_flow(session, flow, "25")
        assert session.variables["age"] == 25.0

    async def test_invalid_number_gives_none(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.USER_INPUT,
                config={"variable": "age", "input_type": "number"},
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="n2", type=NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        session = await resume_flow(session, flow, "not-a-number")
        assert session.variables.get("age") is None

    async def test_choices_validation(self):
        flow = simple_flow(
            Node(
                id="n1",
                type=NodeType.USER_INPUT,
                config={"variable": "choice", "choices": ["yes", "no"]},
                exec_out=ExecOut(fallback="n2"),
            ),
            Node(id="n2", type=NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        session = await resume_flow(session, flow, "maybe")
        assert session.variables.get("choice") is None  # invalid choice

    async def test_waiting_node_id_stored(self):
        flow = simple_flow(
            Node(id="n1", type=NodeType.USER_INPUT, config={}, exec_out=ExecOut(fallback="n2")),
            Node(id="n2", type=NodeType.END),
        )
        session = make_session()
        session = await start_flow(session, flow)
        assert session.variables.get("__waiting_node__") == "n1"
