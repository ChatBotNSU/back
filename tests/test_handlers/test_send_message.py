import pytest

from engine.registry import load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


def make_session(**kw) -> Session:
    return Session(flow_id="f1", **kw)


def make_node(config: dict) -> Node:
    return Node(id="n1", type=NodeType.SEND_MESSAGE, config=config)


class TestSendMessage:
    async def test_plain_text(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        out = await h.execute({"content_type": "text", "text": "Hello!"}, {}, session, make_node({}))
        assert out["message"]["text"] == "Hello!"
        assert out["message"]["content_type"] == "text"

    async def test_template_rendering(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        session.variables["name"] = "Alice"
        out = await h.execute({"text": "Hi {{name}}!"}, {}, session, make_node({}))
        assert out["message"]["text"] == "Hi Alice!"

    async def test_template_uses_data_in(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        out = await h.execute({"text": "Score: {{score}}"}, {"score": 99}, session, make_node({}))
        assert out["message"]["text"] == "Score: 99"

    async def test_message_stored_in_session(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        await h.execute({"text": "msg1"}, {}, session, make_node({}))
        await h.execute({"text": "msg2"}, {}, session, make_node({}))
        assert len(session.variables["__messages__"]) == 2

    async def test_buttons_content_type(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        config = {
            "content_type": "buttons",
            "text": "Choose:",
            "buttons": [{"label": "Yes"}, {"label": "No"}],
        }
        out = await h.execute(config, {}, session, make_node(config))
        assert out["message"]["buttons"] == [{"label": "Yes"}, {"label": "No"}]

    async def test_unknown_placeholder_left_as_is(self):
        from handlers.send_message import SendMessageHandler
        h = SendMessageHandler()
        session = make_session()
        out = await h.execute({"text": "Hi {{ghost}}!"}, {}, session, make_node({}))
        assert "{{ghost}}" in out["message"]["text"]
