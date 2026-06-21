import pytest

from engine.resolver import resolve_data_in, resolve_exec_out, _matches
from models.node import Node, NodeType, DataInPort, ExecOut, ExecCondition
from models.session import Session


def make_node(
    node_id: str = "n1",
    data_in: dict | None = None,
    conditions: list | None = None,
    fallback: str | None = None,
) -> Node:
    return Node(
        id=node_id,
        type=NodeType.SEND_MESSAGE,
        data_in={
            k: DataInPort(**({**v, "from": v.pop("from_", None)} if "from_" in v else v))
            for k, v in (data_in or {}).items()
        },
        exec_out=ExecOut(
            conditions=[ExecCondition(**c) for c in (conditions or [])],
            fallback=fallback,
        ),
    )


def make_session(**kwargs) -> Session:
    return Session(flow_id="flow1", **kwargs)


# ─── resolve_data_in ───────────────────────────────────────────────────────────

class TestResolveDataIn:
    def test_explicit_from_key(self):
        session = make_session()
        session.node_outputs["prev"] = {"phone": "123"}
        node = Node(
            id="n1",
            type=NodeType.SEND_MESSAGE,
            data_in={"phone": DataInPort(**{"from": "prev.phone"})},
        )
        result = resolve_data_in(node, session)
        assert result["phone"] == "123"

    def test_explicit_from_whole_node(self):
        session = make_session()
        session.node_outputs["prev"] = {"a": 1, "b": 2}
        node = Node(
            id="n1",
            type=NodeType.SEND_MESSAGE,
            data_in={"data": DataInPort(**{"from": "prev"})},
        )
        result = resolve_data_in(node, session)
        assert result["data"] == {"a": 1, "b": 2}

    def test_fallback_to_session_variable(self):
        session = make_session()
        session.variables["name"] = "Alice"
        node = Node(
            id="n1",
            type=NodeType.SEND_MESSAGE,
            data_in={"name": DataInPort(type="string")},
        )
        result = resolve_data_in(node, session)
        assert result["name"] == "Alice"

    def test_missing_returns_none(self):
        session = make_session()
        node = Node(
            id="n1",
            type=NodeType.SEND_MESSAGE,
            data_in={"ghost": DataInPort(type="string")},
        )
        result = resolve_data_in(node, session)
        assert result["ghost"] is None

    def test_empty_data_in(self):
        session = make_session()
        node = Node(id="n1", type=NodeType.SEND_MESSAGE)
        result = resolve_data_in(node, session)
        assert result == {}


# ─── resolve_exec_out ─────────────────────────────────────────────────────────

class TestResolveExecOut:
    def test_eq_condition_matches(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[
                    ExecCondition(**{"if": "$data.ok", "eq": True, "goto": "n2"}),
                    ExecCondition(**{"if": "$data.ok", "eq": False, "goto": "n_err"}),
                ]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"ok": True}, session) == "n2"
        assert resolve_exec_out(node, {"ok": False}, session) == "n_err"

    def test_neq_condition(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[ExecCondition(**{"if": "$data.status", "neq": 200, "goto": "err"})]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"status": 404}, session) == "err"
        assert resolve_exec_out(node, {"status": 200}, session) is None

    def test_gt_lt_conditions(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[
                    ExecCondition(**{"if": "$data.score", "gt": 90, "goto": "high"}),
                    ExecCondition(**{"if": "$data.score", "lt": 50, "goto": "low"}),
                ]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"score": 95}, session) == "high"
        assert resolve_exec_out(node, {"score": 40}, session) == "low"
        assert resolve_exec_out(node, {"score": 70}, session) is None

    def test_contains_string(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[ExecCondition(**{"if": "$data.text", "contains": "hello", "goto": "greet"})]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"text": "hello world"}, session) == "greet"
        assert resolve_exec_out(node, {"text": "goodbye"}, session) is None

    def test_contains_list(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[ExecCondition(**{"if": "$data.tags", "contains": "vip", "goto": "vip_flow"})]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"tags": ["user", "vip"]}, session) == "vip_flow"

    def test_exists_not_exists(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[
                    ExecCondition(**{"if": "$data.phone", "exists": True, "goto": "has_phone"}),
                    ExecCondition(**{"if": "$data.email", "not_exists": True, "goto": "no_email"}),
                ]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"phone": "123", "email": None}, session) == "has_phone"
        assert resolve_exec_out(node, {"phone": None, "email": None}, session) == "no_email"

    def test_in_operator(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[ExecCondition(**{"if": "$data.status", "in": ["active", "trial"], "goto": "allowed"})]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"status": "trial"}, session) == "allowed"
        assert resolve_exec_out(node, {"status": "banned"}, session) is None

    def test_fallback_used_when_no_match(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[ExecCondition(**{"if": "$data.ok", "eq": True, "goto": "n2"})],
                fallback="n_default",
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"ok": False}, session) == "n_default"

    def test_session_variable_path(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[ExecCondition(**{"if": "$session.user_id", "exists": True, "goto": "known"})]
            ),
        )
        session = make_session()
        session.variables["user_id"] = "u123"
        assert resolve_exec_out(node, {}, session) == "known"

    def test_nested_dot_path(self):
        node = Node(
            id="n1",
            type=NodeType.INTENT,
            exec_out=ExecOut(
                conditions=[ExecCondition(**{"if": "$data.response.ok", "eq": True, "goto": "ok"})]
            ),
        )
        session = make_session()
        assert resolve_exec_out(node, {"response": {"ok": True}}, session) == "ok"
