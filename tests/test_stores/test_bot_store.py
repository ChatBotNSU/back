"""
Tests for SQLBotStore (via SQLite/aiosqlite).
"""
import pytest

from stores.bot_store import BotConfig, SQLBotStore


@pytest.fixture()
def store(db_session_factory):
    return SQLBotStore(db_session_factory)


def _bot(**kwargs) -> BotConfig:
    import uuid
    return BotConfig(
        id=str(uuid.uuid4()),
        name=kwargs.get("name", "Test Bot"),
        flow_id=kwargs.get("flow_id", "flow-1"),
        channel=kwargs.get("channel", "telegram"),
        token=kwargs.get("token", "tok-" + str(uuid.uuid4())[:8]),
        webhook_secret=kwargs.get("webhook_secret", ""),
    )


class TestSQLBotStore:
    async def test_save_and_get_by_id(self, store):
        bot = _bot(name="Greeter")
        await store.save(bot)
        got = await store.get_by_id(bot.id)
        assert got is not None
        assert got.name == "Greeter"
        assert got.flow_id == bot.flow_id

    async def test_get_by_id_missing(self, store):
        assert await store.get_by_id("ghost") is None

    async def test_get_by_token(self, store):
        bot = _bot(token="tg-abc123")
        await store.save(bot)
        got = await store.get_by_token("tg-abc123")
        assert got is not None
        assert got.id == bot.id

    async def test_get_by_token_missing(self, store):
        assert await store.get_by_token("no-such-token") is None

    async def test_update(self, store):
        bot = _bot(name="OldName")
        await store.save(bot)
        bot.name = "NewName"
        bot.flow_id = "flow-2"
        await store.save(bot)
        got = await store.get_by_id(bot.id)
        assert got.name == "NewName"
        assert got.flow_id == "flow-2"

    async def test_delete(self, store):
        bot = _bot()
        await store.save(bot)
        await store.delete(bot.id)
        assert await store.get_by_id(bot.id) is None

    async def test_delete_nonexistent_noop(self, store):
        await store.delete("ghost")  # should not raise

    async def test_list_all(self, store):
        b1 = _bot(name="A")
        b2 = _bot(name="B")
        await store.save(b1)
        await store.save(b2)
        bots = await store.list_all()
        ids = {b.id for b in bots}
        assert b1.id in ids
        assert b2.id in ids

    async def test_all_fields_preserved(self, store):
        bot = BotConfig(
            id="full-bot",
            name="Full",
            flow_id="f99",
            channel="whatsapp",
            token="wa-token",
            webhook_secret="secret-abc",
            metadata={"plan": "pro"},
        )
        await store.save(bot)
        got = await store.get_by_id("full-bot")
        assert got.channel == "whatsapp"
        assert got.token == "wa-token"
        assert got.webhook_secret == "secret-abc"
        assert got.metadata["plan"] == "pro"
