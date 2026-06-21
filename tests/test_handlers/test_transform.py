import pytest

from engine.registry import load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


def make_session(**kw) -> Session:
    return Session(flow_id="f1", **kw)


def make_node() -> Node:
    return Node(id="n1", type=NodeType.TRANSFORM)


class TestTransform:
    async def test_simple_mapping(self):
        from handlers.transform import TransformHandler
        h = TransformHandler()
        session = make_session()
        session.variables["first"] = "John"
        session.variables["last"] = "Doe"
        config = {
            "mappings": [
                {"from": "{{first}}", "to": "given_name"},
                {"from": "{{last}}", "to": "family_name"},
            ]
        }
        out = await h.execute(config, {}, session, make_node())
        assert out["result"]["given_name"] == "John"
        assert out["result"]["family_name"] == "Doe"

    async def test_mapping_from_data_in(self):
        from handlers.transform import TransformHandler
        h = TransformHandler()
        session = make_session()
        config = {"mappings": [{"from": "{{score}}", "to": "points"}]}
        out = await h.execute(config, {"score": "100"}, session, make_node())
        assert out["result"]["points"] == "100"

    async def test_output_var_saved(self):
        from handlers.transform import TransformHandler
        h = TransformHandler()
        session = make_session()
        session.variables["x"] = "val"
        config = {
            "mappings": [{"from": "{{x}}", "to": "y"}],
            "output_var": "mapped",
        }
        await h.execute(config, {}, session, make_node())
        assert session.variables["mapped"]["y"] == "val"

    async def test_empty_mappings(self):
        from handlers.transform import TransformHandler
        h = TransformHandler()
        session = make_session()
        out = await h.execute({"mappings": []}, {}, session, make_node())
        assert out["result"] == {}

    async def test_static_value_mapping(self):
        from handlers.transform import TransformHandler
        h = TransformHandler()
        session = make_session()
        config = {"mappings": [{"from": "static-value", "to": "field"}]}
        out = await h.execute(config, {}, session, make_node())
        assert out["result"]["field"] == "static-value"
