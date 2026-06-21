"""Tests for webhook endpoints — uses SQLite + fakeredis via conftest."""
import pytest

from engine.registry import load_all_handlers
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from stores.bot_store import BotConfig

load_all_handlers()

BOT_TOKEN = "test-telegram-token-123"
BOT_ID = "test-bot-id-1"

SIMPLE_FLOW = Flow(
    id="webhook-flow-1",
    start_node="n1",
    nodes={
        "n1": Node(
            id="n1",
            type=NodeType.SEND_MESSAGE,
            config={"text": "Hello {{user_meta.first_name}}!"},
            exec_out=ExecOut(fallback="n2"),
        ),
        "n2": Node(id="n2", type=NodeType.END),
    },
)

BOT = BotConfig(
    id=BOT_ID,
    name="Test Bot",
    flow_id=SIMPLE_FLOW.id,
    channel="telegram",
    token=BOT_TOKEN,
)

TG_UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 100,
        "from": {"id": 999, "first_name": "Alice", "username": "alice", "language_code": "ru"},
        "chat": {"id": 999, "type": "private"},
        "text": "Hello",
    },
}


@pytest.fixture()
async def seeded_client(client, flow_store, bot_store):
    await flow_store.save(SIMPLE_FLOW)
    await bot_store.save(BOT)
    return client


class TestTelegramWebhook:
    async def test_returns_ok(self, seeded_client):
        resp = seeded_client.post(f"/webhook/telegram/{BOT_TOKEN}", json=TG_UPDATE)
        assert resp.status_code == 200
        assert resp.json()["ok"] == "true"

    async def test_unknown_token_still_200(self, seeded_client):
        resp = seeded_client.post("/webhook/telegram/wrong-token", json=TG_UPDATE)
        assert resp.status_code == 200

    async def test_no_message_still_200(self, seeded_client):
        resp = seeded_client.post(f"/webhook/telegram/{BOT_TOKEN}", json={"update_id": 2})
        assert resp.status_code == 200

    async def test_edited_message_accepted(self, seeded_client):
        payload = {
            "update_id": 3,
            "edited_message": {
                "message_id": 101,
                "from": {"id": 999, "first_name": "Alice"},
                "chat": {"id": 999, "type": "private"},
                "text": "Edited",
            },
        }
        resp = seeded_client.post(f"/webhook/telegram/{BOT_TOKEN}", json=payload)
        assert resp.status_code == 200


class TestGenericWebhook:
    async def test_known_bot_returns_ok(self, seeded_client):
        resp = seeded_client.post(
            f"/webhook/generic/{BOT_ID}",
            json={"user_id": "u1", "text": "hi"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] == "true"

    async def test_unknown_bot_returns_404(self, seeded_client):
        resp = seeded_client.post("/webhook/generic/ghost-bot", json={"text": "hi"})
        assert resp.status_code == 404


class TestWaitEventDelivery:
    async def test_event_to_nonexistent_session(self, client):
        resp = client.post("/webhook/event/ghost-session/key1", json={"data": "x"})
        assert resp.status_code == 404

    async def test_event_to_non_waiting_session(self, client, session_store):
        from models.session import Session, SessionState
        session = Session(flow_id="f1")
        session.state = SessionState.DONE
        await session_store.save(session)

        resp = client.post(f"/webhook/event/{session.id}/key1", json={"data": "x"})
        assert resp.status_code == 409


class TestHealthCheck:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestBotsAPI:
    def test_create_bot(self, client):
        resp = client.post("/api/bots", json={
            "name": "MyBot",
            "flow_id": "f1",
            "channel": "telegram",
            "token": "tok-123",
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "MyBot"
        assert "webhook_url" in resp.json()

    def test_list_bots(self, client):
        client.post("/api/bots", json={"name": "Bot1", "flow_id": "f1", "channel": "telegram"})
        client.post("/api/bots", json={"name": "Bot2", "flow_id": "f2", "channel": "whatsapp"})
        resp = client.get("/api/bots")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_get_bot(self, client):
        created = client.post("/api/bots", json={
            "name": "GetBot", "flow_id": "f1", "channel": "telegram"
        }).json()
        resp = client.get(f"/api/bots/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_bot_not_found(self, client):
        resp = client.get("/api/bots/ghost")
        assert resp.status_code == 404

    def test_delete_bot(self, client):
        created = client.post("/api/bots", json={
            "name": "DelBot", "flow_id": "f1", "channel": "telegram"
        }).json()
        resp = client.delete(f"/api/bots/{created['id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/bots/{created['id']}").status_code == 404
