import pytest

from engine.registry import load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


def make_session(**kw) -> Session:
    return Session(flow_id="f1", **kw)


def make_node() -> Node:
    return Node(id="n1", type=NodeType.INTENT)


INTENTS_CONFIG = {
    "intents": [
        {"name": "greet", "keywords": ["hello", "hi", "hey"]},
        {"name": "bye", "keywords": ["bye", "goodbye"]},
        {"name": "order", "keywords": ["order", "buy", "purchase"]},
    ],
    "input_var": "text",
    "confidence": 0.3,
    "fallback": "unknown",
}


class TestIntent:
    async def test_matches_greet(self):
        from handlers.intent import IntentHandler
        h = IntentHandler()
        session = make_session()
        session.variables["text"] = "hello there"
        out = await h.execute(INTENTS_CONFIG, {"text": "hello there"}, session, make_node())
        assert out["intent"] == "greet"
        assert out["matched"] is True
        assert out["confidence"] > 0

    async def test_fallback_on_no_match(self):
        from handlers.intent import IntentHandler
        h = IntentHandler()
        session = make_session()
        out = await h.execute(INTENTS_CONFIG, {"text": "random stuff"}, session, make_node())
        assert out["intent"] == "unknown"
        assert out["matched"] is False

    async def test_uses_data_in_text(self):
        from handlers.intent import IntentHandler
        h = IntentHandler()
        session = make_session()
        out = await h.execute(INTENTS_CONFIG, {"text": "I want to buy something"}, session, make_node())
        assert out["intent"] == "order"

    async def test_high_confidence_threshold_blocks_partial(self):
        from handlers.intent import IntentHandler
        h = IntentHandler()
        session = make_session()
        config = {**INTENTS_CONFIG, "confidence": 0.9}
        # "hello" matches 1/3 keywords → confidence ~0.33, below threshold
        out = await h.execute(config, {"text": "hello"}, session, make_node())
        assert out["intent"] == "unknown"

    async def test_empty_intents_returns_fallback(self):
        from handlers.intent import IntentHandler
        h = IntentHandler()
        session = make_session()
        out = await h.execute({"intents": [], "fallback": "none"}, {"text": "hi"}, session, make_node())
        assert out["intent"] == "none"
