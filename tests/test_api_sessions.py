"""Tests for /api/sessions — uses SQLite + fakeredis via conftest."""
import pytest

from engine.registry import load_all_handlers
from engine.runner import start_flow
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from models.session import Session, SessionState

load_all_handlers()


def _waiting_flow(flow_id: str) -> Flow:
    return Flow(
        id=flow_id,
        start_node="n1",
        nodes={
            "n1": Node(
                id="n1",
                type=NodeType.USER_INPUT,
                config={"variable": "name"},
                exec_out=ExecOut(fallback="n2"),
            ),
            "n2": Node(id="n2", type=NodeType.END),
        },
    )


def _done_flow(flow_id: str) -> Flow:
    return Flow(
        id=flow_id,
        start_node="n1",
        nodes={"n1": Node(id="n1", type=NodeType.END)},
    )


class TestSessionsAPI:
    async def test_get_session(self, client, flow_store, session_store):
        flow = _waiting_flow("f-get")
        session = Session(flow_id="f-get")
        session = await start_flow(session, flow)
        await flow_store.save(flow)
        await session_store.save(session)

        resp = client.get(f"/api/sessions/{session.id}")
        assert resp.status_code == 200
        assert resp.json()["state"] == "waiting"

    async def test_get_session_not_found(self, client):
        resp = client.get("/api/sessions/ghost-id")
        assert resp.status_code == 404

    async def test_resume_session(self, client, flow_store, session_store):
        flow = _waiting_flow("f-resume")
        session = Session(flow_id="f-resume")
        session = await start_flow(session, flow)
        await flow_store.save(flow)
        await session_store.save(session)

        resp = client.post(f"/api/sessions/{session.id}/resume", json={"message": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "done"
        assert data["variables"]["name"] == "Alice"

    async def test_resume_non_waiting_fails(self, client, flow_store, session_store):
        flow = _done_flow("f-done")
        session = Session(flow_id="f-done")
        session = await start_flow(session, flow)
        await flow_store.save(flow)
        await session_store.save(session)

        resp = client.post(f"/api/sessions/{session.id}/resume", json={"message": "hi"})
        assert resp.status_code == 409

    async def test_resume_missing_flow_fails(self, client, session_store):
        session = Session(flow_id="no-flow")
        session.state = SessionState.WAITING
        await session_store.save(session)

        resp = client.post(f"/api/sessions/{session.id}/resume", json={"message": "hi"})
        assert resp.status_code == 404

    async def test_get_trace(self, client, flow_store, session_store):
        flow = _waiting_flow("f-trace")
        session = Session(flow_id="f-trace")
        session = await start_flow(session, flow)
        await flow_store.save(flow)
        await session_store.save(session)

        resp = client.get(f"/api/sessions/{session.id}/trace")
        assert resp.status_code == 200
        data = resp.json()
        assert "trace" in data
        assert data["state"] == "waiting"
        assert data["steps_count"] >= 1

    async def test_list_sessions_by_flow(self, client, session_store):
        s1 = Session(flow_id="f-list")
        s2 = Session(flow_id="f-list")
        s3 = Session(flow_id="other-flow")
        for s in (s1, s2, s3):
            await session_store.save(s)

        resp = client.get("/api/sessions?flow_id=f-list")
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()}
        assert s1.id in ids
        assert s2.id in ids
        assert s3.id not in ids

    async def test_delete_session(self, client, session_store):
        session = Session(flow_id="f-del")
        await session_store.save(session)

        resp = client.delete(f"/api/sessions/{session.id}")
        assert resp.status_code == 204
        assert client.get(f"/api/sessions/{session.id}").status_code == 404

    async def test_delete_session_not_found(self, client):
        resp = client.delete("/api/sessions/ghost-id")
        assert resp.status_code == 404

    async def test_variables_returned_in_detail(self, client, flow_store, session_store):
        flow = _waiting_flow("f-vars")
        session = Session(flow_id="f-vars")
        session.variables["city"] = "Moscow"
        session = await start_flow(session, flow)
        await flow_store.save(flow)
        await session_store.save(session)

        resp = client.get(f"/api/sessions/{session.id}")
        assert resp.json()["variables"]["city"] == "Moscow"

    async def test_two_resume_steps(self, client, flow_store, session_store):
        flow = Flow(
            id="f-two-steps",
            start_node="n1",
            nodes={
                "n1": Node(id="n1", type=NodeType.USER_INPUT, config={"variable": "city"}, exec_out=ExecOut(fallback="n2")),
                "n2": Node(id="n2", type=NodeType.USER_INPUT, config={"variable": "name"}, exec_out=ExecOut(fallback="n3")),
                "n3": Node(id="n3", type=NodeType.END),
            },
        )
        session = Session(flow_id="f-two-steps")
        session = await start_flow(session, flow)
        await flow_store.save(flow)
        await session_store.save(session)

        resp = client.post(f"/api/sessions/{session.id}/resume", json={"message": "Moscow"})
        assert resp.json()["state"] == "waiting"
        assert resp.json()["variables"]["city"] == "Moscow"

        sid = resp.json()["id"]
        resp2 = client.post(f"/api/sessions/{sid}/resume", json={"message": "Alice"})
        assert resp2.json()["state"] == "done"
        assert resp2.json()["variables"]["name"] == "Alice"
