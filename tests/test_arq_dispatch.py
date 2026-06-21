"""Tests for ARQ enqueue dispatch from webhooks (fake pool) + BackgroundTasks fallback."""
from __future__ import annotations

import pytest

from api.deps import get_arq_pool
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from models.session import SessionState
from stores.bot_store import BotConfig

_FLOW = Flow(id="arq-flow", start_node="n1", nodes={
    "n1": Node(id="n1", type=NodeType.SEND_MESSAGE, config={"text": "hi"}, exec_out=ExecOut(fallback="n2")),
    "n2": Node(id="n2", type=NodeType.END),
})


class FakePool:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, name, **kwargs):
        self.jobs.append((name, kwargs))
        return object()


@pytest.fixture()
async def seeded(flow_store, bot_store):
    await flow_store.save(_FLOW)
    await bot_store.save(BotConfig(id="arq-bot", name="b", flow_id="arq-flow", channel="generic"))


class TestArqEnqueue:
    def test_enqueues_when_pool_present(self, client, seeded):
        pool = FakePool()
        client.app.dependency_overrides[get_arq_pool] = lambda: pool

        resp = client.post("/webhook/generic/arq-bot", json={"user_id": "u1", "text": "hello"})
        assert resp.status_code == 200
        assert len(pool.jobs) == 1
        name, kwargs = pool.jobs[0]
        assert name == "run_flow_task"
        assert kwargs["flow_id"] == "arq-flow"
        assert kwargs["session_id"] is None  # new conversation
        assert kwargs["user_text"] == "hello"

    async def test_fallback_runs_inline(self, client, seeded, session_store):
        # No pool override → arq_pool is None → BackgroundTasks runs the flow now.
        resp = client.post("/webhook/generic/arq-bot", json={"user_id": "u2", "text": "hi"})
        assert resp.status_code == 200
        sessions = await session_store.list_by_flow("arq-flow")
        assert len(sessions) == 1
        assert sessions[0].state == SessionState.DONE
