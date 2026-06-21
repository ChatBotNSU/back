"""Tests for analytics service + /api/analytics endpoints."""
from __future__ import annotations

from engine.registry import load_all_handlers
from engine.runner import start_flow
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from models.session import Session, SessionState
from services.analytics import compute_dropoff, compute_overview

load_all_handlers()


def _flow(flow_id: str) -> Flow:
    return Flow(
        id=flow_id,
        name="Funnel",
        start_node="m1",
        nodes={
            "m1": Node(id="m1", type=NodeType.SEND_MESSAGE, label="Greet",
                       config={"text": "hi"}, exec_out=ExecOut(fallback="q1")),
            "q1": Node(id="q1", type=NodeType.USER_INPUT, label="Ask",
                       config={"variable": "name"}, exec_out=ExecOut(fallback="e1")),
            "e1": Node(id="e1", type=NodeType.END, label="Done"),
        },
    )


def _session(flow_id, state, outputs, current=None, steps=0) -> Session:
    return Session(
        flow_id=flow_id,
        state=state,
        current_node=current,
        node_outputs={k: {} for k in outputs},
        steps_count=steps,
    )


class TestComputeOverview:
    def test_overview_basic(self):
        flow = _flow("f1")
        sessions = [
            _session("f1", SessionState.DONE, ["m1", "q1", "e1"], steps=3),
            _session("f1", SessionState.WAITING, ["m1", "q1"], current="q1", steps=2),
            _session("f1", SessionState.WAITING, ["m1"], current="m1", steps=1),
        ]
        ov = compute_overview(flow, sessions)
        assert ov["total_sessions"] == 3
        assert ov["completed"] == 1
        assert ov["conversion_rate"] == round(1 / 3, 4)
        assert ov["messages_sent"] == 3  # m1 visited in all 3
        assert ov["by_state"] == {"done": 1, "waiting": 2}
        assert ov["node_visits"]["m1"] == 3
        assert ov["node_visits"]["q1"] == 2

    def test_overview_empty(self):
        ov = compute_overview(_flow("f1"), [])
        assert ov["total_sessions"] == 0
        assert ov["conversion_rate"] == 0.0
        assert ov["avg_steps"] == 0.0


class TestComputeDropoff:
    def test_dropoff_ranks_stuck_nodes(self):
        flow = _flow("f1")
        sessions = [
            _session("f1", SessionState.DONE, ["m1", "q1", "e1"]),  # converted → ignored
            _session("f1", SessionState.WAITING, ["m1", "q1"], current="q1"),
            _session("f1", SessionState.WAITING, ["m1", "q1"], current="q1"),
            _session("f1", SessionState.ERROR, ["m1"], current="m1"),
        ]
        rows = compute_dropoff(flow, sessions)
        assert rows[0]["node_id"] == "q1"
        assert rows[0]["count"] == 2
        assert rows[0]["label"] == "Ask"
        assert {r["node_id"] for r in rows} == {"q1", "m1"}


class TestAnalyticsAPI:
    async def test_overview_endpoint(self, client, flow_store, session_store):
        flow = _flow("f-api")
        await flow_store.save(flow)
        s = Session(flow_id="f-api")
        s = await start_flow(s, flow)  # runs m1 → pauses at q1 (user_input)
        await session_store.save(s)

        resp = client.get("/api/analytics/flows/f-api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 1
        assert data["messages_sent"] == 1
        assert data["by_state"] == {"waiting": 1}

    async def test_dropoff_endpoint(self, client, flow_store, session_store):
        flow = _flow("f-drop")
        await flow_store.save(flow)
        s = Session(flow_id="f-drop")
        s = await start_flow(s, flow)
        await session_store.save(s)

        resp = client.get("/api/analytics/flows/f-drop/dropoff")
        assert resp.status_code == 200
        assert resp.json()["dropoff"][0]["node_id"] == "q1"

    def test_overview_flow_not_found(self, client):
        assert client.get("/api/analytics/flows/ghost/overview").status_code == 404


class TestProjectAnalytics:
    async def test_project_rollup(self, client, flow_store, session_store):
        pid = client.post("/api/projects", json={"name": "An"}).json()["id"]
        flow = _flow("pf1")
        flow.project_id = pid
        flow.workspace_id = "default"
        await flow_store.save(flow)
        s = await start_flow(Session(flow_id="pf1", project_id=pid), flow)
        await session_store.save(s)

        resp = client.get(f"/api/analytics/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["flows"] == 1
        assert data["totals"]["sessions"] == 1
        assert data["totals"]["messages_sent"] == 1
        assert data["flows"][0]["flow_id"] == "pf1"

    def test_project_not_found(self, client):
        assert client.get("/api/analytics/projects/ghost").status_code == 404
