"""Tests for the dead-letter store + /api/dead-letter endpoints + webhook wiring."""
from __future__ import annotations

from engine.registry import load_all_handlers
from models.flow import Flow
from models.node import Node, NodeType
from stores.bot_store import BotConfig
from stores.dead_letter import DeadLetterEntry, InMemoryDeadLetterStore

load_all_handlers()

# start_node points to a non-existent node → runner ends in ERROR state.
ERR_FLOW = Flow(
    id="err-flow",
    start_node="missing",
    nodes={"only": Node(id="only", type=NodeType.END)},
)


class TestInMemoryStore:
    async def test_push_list_count(self):
        store = InMemoryDeadLetterStore()
        await store.push(DeadLetterEntry(flow_id="f", error="boom"))
        await store.push(DeadLetterEntry(flow_id="g", error="bang"))
        assert await store.count() == 2
        entries = await store.list()
        assert entries[0].flow_id == "g"  # newest first
        assert entries[1].flow_id == "f"

    async def test_clear(self):
        store = InMemoryDeadLetterStore()
        await store.push(DeadLetterEntry(flow_id="f", error="x"))
        await store.clear()
        assert await store.count() == 0

    async def test_max_len_cap(self):
        store = InMemoryDeadLetterStore(max_len=3)
        for i in range(5):
            await store.push(DeadLetterEntry(flow_id=str(i), error="x"))
        assert await store.count() == 3
        assert [e.flow_id for e in await store.list()] == ["4", "3", "2"]


class TestDeadLetterAPI:
    async def test_list_and_clear(self, client, dead_letter_store):
        await dead_letter_store.push(DeadLetterEntry(flow_id="f1", error="oops"))
        resp = client.get("/api/dead-letter")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["entries"][0]["flow_id"] == "f1"
        assert body["entries"][0]["error"] == "oops"

        assert client.delete("/api/dead-letter").status_code == 204
        assert client.get("/api/dead-letter").json()["count"] == 0


class TestWebhookDeadLetterWiring:
    async def test_flow_error_recorded(self, client, flow_store, bot_store, dead_letter_store):
        await flow_store.save(ERR_FLOW)
        await bot_store.save(
            BotConfig(id="err-bot", name="e", flow_id="err-flow", channel="generic")
        )
        resp = client.post("/webhook/generic/err-bot", json={"text": "hi", "user_id": "u"})
        assert resp.status_code == 200

        assert await dead_letter_store.count() == 1
        entry = (await dead_letter_store.list())[0]
        assert entry.kind == "flow_error"
        assert entry.flow_id == "err-flow"

    async def test_missing_flow_recorded(self, client, bot_store, dead_letter_store):
        await bot_store.save(
            BotConfig(id="nf-bot", name="e", flow_id="does-not-exist", channel="generic")
        )
        client.post("/webhook/generic/nf-bot", json={"text": "hi", "user_id": "u"})
        entries = await dead_letter_store.list()
        assert len(entries) == 1
        assert entries[0].error == "Flow not found"
