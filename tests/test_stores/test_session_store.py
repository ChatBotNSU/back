"""
Tests for RedisSessionStore (via fakeredis).
"""
import pytest

from models.session import Session, SessionState
from stores.session_store import RedisSessionStore


@pytest.fixture()
async def store(redis_client):
    return RedisSessionStore(redis_client, ttl=3600)


def _session(flow_id: str = "f1", session_key: str = "") -> Session:
    s = Session(flow_id=flow_id)
    if session_key:
        s.variables["__session_key__"] = session_key
    return s


class TestRedisSessionStore:
    async def test_save_and_get(self, store):
        s = _session()
        await store.save(s)
        got = await store.get(s.id)
        assert got is not None
        assert got.id == s.id
        assert got.flow_id == s.flow_id

    async def test_get_missing_returns_none(self, store):
        assert await store.get("nonexistent") is None

    async def test_get_by_key(self, store):
        s = _session(session_key="bot1:user99")
        await store.save(s)
        got = await store.get_by_key("bot1:user99")
        assert got is not None
        assert got.id == s.id

    async def test_get_by_key_missing(self, store):
        assert await store.get_by_key("no-such-key") is None

    async def test_save_updates_state(self, store):
        s = _session()
        await store.save(s)
        s.state = SessionState.WAITING
        s.current_node = "n5"
        await store.save(s)
        got = await store.get(s.id)
        assert got.state == SessionState.WAITING
        assert got.current_node == "n5"

    async def test_delete(self, store):
        s = _session(session_key="bot1:userX")
        await store.save(s)
        await store.delete(s.id)
        assert await store.get(s.id) is None
        assert await store.get_by_key("bot1:userX") is None

    async def test_delete_nonexistent_noop(self, store):
        await store.delete("ghost")  # should not raise

    async def test_list_by_flow(self, store):
        s1 = _session("flow-A")
        s2 = _session("flow-A")
        s3 = _session("flow-B")
        for s in (s1, s2, s3):
            await store.save(s)

        result = await store.list_by_flow("flow-A")
        ids = {r.id for r in result}
        assert s1.id in ids
        assert s2.id in ids
        assert s3.id not in ids

    async def test_list_by_flow_limit(self, store):
        for _ in range(5):
            await store.save(_session("flow-Z"))
        result = await store.list_by_flow("flow-Z", limit=3)
        assert len(result) == 3

    async def test_list_by_flow_ordered_by_updated_at(self, store):
        s1 = _session("flow-C")
        s2 = _session("flow-C")
        await store.save(s1)
        await store.save(s2)
        # Touch s1 again to make it more recent
        s1.variables["x"] = 1
        await store.save(s1)

        result = await store.list_by_flow("flow-C")
        assert result[0].id == s1.id

    async def test_variables_survive_round_trip(self, store):
        s = _session()
        s.variables["name"] = "Alice"
        s.variables["score"] = 42
        s.node_outputs["n1"] = {"result": "ok"}
        await store.save(s)
        got = await store.get(s.id)
        assert got.variables["name"] == "Alice"
        assert got.variables["score"] == 42
        assert got.node_outputs["n1"] == {"result": "ok"}

    async def test_session_key_index_updates_on_resave(self, store):
        s = _session(session_key="bot:u1")
        await store.save(s)
        s.state = SessionState.DONE
        await store.save(s)
        got = await store.get_by_key("bot:u1")
        assert got.state == SessionState.DONE
