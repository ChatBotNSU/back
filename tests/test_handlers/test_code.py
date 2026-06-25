"""Tests for the sandboxed code handler (subprocess + rlimits)."""
from __future__ import annotations

import pytest

from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


def _node() -> Node:
    return Node(id="c", type=NodeType.CODE)


async def _run(config, session=None):
    handler = get(NodeType.CODE)
    return await handler.execute(
        config=config,
        data_in=config.get("__data_in__", {}),
        session=session or Session(flow_id="t"),
        node=_node(),
    )


class TestCodeHandler:
    async def test_basic_result(self):
        out = await _run({
            "language": "python",
            "source": "__result__ = a + b",
            "input_vars": ["a", "b"],
            "__data_in__": {"a": 2, "b": 3},
        })
        assert out["result"] == 5
        assert out["error"] is None
        assert out["duration_ms"] >= 0

    async def test_reads_session_variables(self):
        session = Session(flow_id="t", variables={"x": 10})
        out = await _run(
            {"language": "python", "source": "__result__ = x * 2", "input_vars": ["x"]},
            session=session,
        )
        assert out["result"] == 20

    async def test_exception_captured(self):
        out = await _run({
            "language": "python",
            "source": "__result__ = 1 / 0",
        })
        assert out["result"] is None
        assert out["error"] is not None

    async def test_infinite_loop_times_out(self):
        out = await _run({
            "language": "python",
            "source": "while True:\n    pass",
            "timeout_ms": 400,
        })
        assert out["result"] is None
        assert out["error"] is not None  # "Timeout" or terminated by CPU limit

    async def test_memory_limit_enforced(self):
        out = await _run({
            "language": "python",
            "source": "__result__ = len(bytearray(600 * 1024 * 1024))",
            "memory_mb": 64,
        })
        assert out["result"] is None
        assert out["error"] is not None

    async def test_language_is_ignored_runs_python(self):
        # `language` is legacy/no-op now — the node always runs Python.
        out = await _run({"language": "js", "source": "__result__ = 1 + 1"})
        assert out["result"] == 2
        assert out["error"] is None
