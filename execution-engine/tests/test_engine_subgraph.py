"""Smoke tests for the engine: subgraph by-reference semantics + dynamic vars.

These are intentionally narrow. They drive `Engine.execute` directly so we
don't depend on Redis, MinIO, or the sandbox runner. The harder integration
paths (full Redis loop, real MinIO) are left for follow-up.
"""

from __future__ import annotations

import pytest

from models.chatbot import Chatbot, Subgraph, Graph
from models.nodes import (
    SubgraphCall,
    SubgraphExit,
    SetVariable,
    SendMessage,
    SetMessage,
    ConditionNode,
    Branch,
    Condition,
)
from models.execution_state import ExecutionState, Frame
from models.message import InMessage
from engine.engine import Engine


def _state(node_id: str, vars_: dict) -> ExecutionState:
    return ExecutionState(
        bot_id=1,
        execution_id=1,
        call_stack=[Frame(executing_node_id=node_id, variable_values=vars_)],
    )


def _build_if_part_subgraph() -> Subgraph:
    """Subgraph that modifies its input `y` by reference based on a threshold.

    Exits: 'small' (y was below threshold) / 'big' (y was at or above).
    Creates an internal local `thr` that must NOT leak into the caller.
    """
    return Subgraph(
        name="if_part",
        inputs=["y"],
        exits=["small", "big"],
        graph=Graph(root="s_thr", nodes={
            "s_thr": SetVariable(assigned_variable="thr", operation="=", operand=10.0, next_node_id="s_cond"),
            "s_cond": ConditionNode(
                branches=[Branch(
                    condition=Condition(variable_left="y", operation="<", variable_right="thr"),
                    next_node_id="s_set_small",
                )],
                default_next_node_id="s_set_big",
            ),
            "s_set_small": SetVariable(assigned_variable="y", operation="=", operand=20.0, next_node_id="s_exit_small"),
            "s_set_big":   SetVariable(assigned_variable="y", operation="=", operand=10.0, next_node_id="s_exit_big"),
            "s_exit_small": SubgraphExit(exit_label="small"),
            "s_exit_big":   SubgraphExit(exit_label="big"),
        }),
    )


def _build_subgraph_bot() -> Chatbot:
    sub = _build_if_part_subgraph()
    return Chatbot(
        bot_id=1, bot_name="b",
        subgraphs={"if_part": sub},
        graph=Graph(root="n_call", nodes={
            "n_call": SubgraphCall(
                subgraph_name="if_part",
                input_bindings={"y": "y"},
                exit_next_nodes={"small": "n_small", "big": "n_big"},
            ),
            "n_small": SetMessage(text="small y={y}", audios=[], images=[], files=[], choise_options=[], next_node_id="n_send"),
            "n_big":   SetMessage(text="big y={y}",   audios=[], images=[], files=[], choise_options=[], next_node_id="n_send"),
            "n_send":  SendMessage(next_node_id="n_call"),
        }),
    )


@pytest.mark.asyncio
async def test_subgraph_call_modifies_input_by_reference_small_branch():
    bot = _build_subgraph_bot()
    engine = Engine(bot, _state("n_call", {"y": 3.0}))

    msg = await engine.execute(InMessage(text=""))

    assert msg.text == "small y=20.0"
    assert engine.execution_state.call_stack[0].variable_values == {"y": 20.0}


@pytest.mark.asyncio
async def test_subgraph_call_modifies_input_by_reference_big_branch():
    bot = _build_subgraph_bot()
    engine = Engine(bot, _state("n_call", {"y": 50.0}))

    msg = await engine.execute(InMessage(text=""))

    assert msg.text == "big y=10.0"
    assert engine.execution_state.call_stack[0].variable_values == {"y": 10.0}


@pytest.mark.asyncio
async def test_subgraph_locals_do_not_leak_into_caller():
    """The subgraph creates `thr` internally; the caller must never see it."""
    bot = _build_subgraph_bot()
    engine = Engine(bot, _state("n_call", {"y": 3.0}))

    await engine.execute(InMessage(text=""))

    caller_vars = engine.execution_state.call_stack[0].variable_values
    assert "thr" not in caller_vars
    assert set(caller_vars.keys()) == {"y"}


@pytest.mark.asyncio
async def test_subgraph_call_with_renamed_binding():
    """Caller's variable `count` is bound to the subgraph's input parameter `y`."""
    sub = _build_if_part_subgraph()
    bot = Chatbot(
        bot_id=2, bot_name="renamed",
        subgraphs={"if_part": sub},
        graph=Graph(root="n_call", nodes={
            "n_call": SubgraphCall(
                subgraph_name="if_part",
                input_bindings={"y": "count"},
                exit_next_nodes={"small": "n_msg", "big": "n_msg"},
            ),
            "n_msg":  SetMessage(text="count={count}", audios=[], images=[], files=[], choise_options=[], next_node_id="n_send"),
            "n_send": SendMessage(next_node_id="n_call"),
        }),
    )
    engine = Engine(bot, _state("n_call", {"count": 7.0}))

    msg = await engine.execute(InMessage(text=""))

    # 7 < 10 -> small branch, sub sets y=20 -> writes back to caller's `count`.
    assert msg.text == "count=20.0"
    assert engine.execution_state.call_stack[0].variable_values == {"count": 20.0}


@pytest.mark.asyncio
async def test_missing_input_binding_fails_gracefully():
    """If the caller forgets to bind a declared subgraph input, FailExecutor kicks in."""
    sub = _build_if_part_subgraph()
    bot = Chatbot(
        bot_id=3, bot_name="bad",
        subgraphs={"if_part": sub},
        graph=Graph(root="n_call", nodes={
            "n_call": SubgraphCall(
                subgraph_name="if_part",
                input_bindings={},  # 'y' is required but unbound
                exit_next_nodes={"small": "n_send", "big": "n_send"},
            ),
            "n_send": SendMessage(next_node_id="n_call"),
        }),
    )
    engine = Engine(bot, _state("n_call", {}))

    msg = await engine.execute(InMessage(text=""))

    assert msg.text is not None
    assert "missing bindings" in msg.text
    assert "'y'" in msg.text or "y" in msg.text


@pytest.mark.asyncio
async def test_setvariable_dynamic_typing_numeric_and_string():
    """Plain assignment preserves operand's type; += adapts to operands."""
    bot = Chatbot(
        bot_id=4, bot_name="dyn",
        graph=Graph(root="n_init", nodes={
            "n_init":  SetVariable(assigned_variable="name", operation="=", operand="John", next_node_id="n_concat"),
            "n_concat": SetVariable(assigned_variable="name", operation="+=", operand=" Smith", next_node_id="n_msg"),
            "n_msg":   SetMessage(text="hi {name}", audios=[], images=[], files=[], choise_options=[], next_node_id="n_send"),
            "n_send":  SendMessage(next_node_id="n_init"),
        }),
    )
    engine = Engine(bot, _state("n_init", {}))

    msg = await engine.execute(InMessage(text=""))

    assert msg.text == "hi John Smith"
