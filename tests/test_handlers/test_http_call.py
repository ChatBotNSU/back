import pytest

from engine.registry import load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


def make_session(**kw) -> Session:
    return Session(flow_id="f1", **kw)


def make_node(config: dict) -> Node:
    return Node(id="n1", type=NodeType.HTTP_CALL, config=config)


class TestHttpCall:
    async def test_stub_returns_ok(self):
        from handlers.http_call import HttpCallHandler
        h = HttpCallHandler()
        session = make_session()
        config = {
            "method": "GET",
            "url": "http://stub",
            "__test_response__": {"id": 1},
        }
        out = await h.execute(config, {}, session, make_node(config))
        assert out["ok"] is True
        assert out["status"] == 200
        assert out["response"] == {"id": 1}

    async def test_url_template_rendered(self):
        from handlers.http_call import HttpCallHandler
        h = HttpCallHandler()
        session = make_session()
        session.variables["user_id"] = "42"
        config = {
            "method": "GET",
            "url": "http://api/users/{{user_id}}",
            "__test_response__": {},
        }
        # We just check it doesn't crash with template url
        out = await h.execute(config, {}, session, make_node(config))
        assert out["ok"] is True

    async def test_duration_ms_present(self):
        from handlers.http_call import HttpCallHandler
        h = HttpCallHandler()
        session = make_session()
        config = {"method": "GET", "url": "http://x", "__test_response__": {}}
        out = await h.execute(config, {}, session, make_node(config))
        assert "duration_ms" in out
