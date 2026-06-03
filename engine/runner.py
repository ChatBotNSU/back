from __future__ import annotations

import logging
import time
from copy import deepcopy
from typing import Any, Awaitable, Callable

from engine import registry, resolver
from models.flow import Flow
from models.node import NodeType
from models.session import Session, SessionState
from services import metrics

logger = logging.getLogger(__name__)

# Nodes that pause execution and wait for external input
WAITING_NODES = {
    NodeType.USER_INPUT,
    NodeType.WAIT,
    NodeType.HANDOFF,
    NodeType.SLOT_FILL,
}

FlowLoader = Callable[[str], Awaitable[Flow | None]]


async def run_step(
    session: Session,
    flow: Flow,
    flow_loader: FlowLoader | None = None,
) -> Session:
    """
    Execute one step of the flow. Recursively continues until the session
    reaches WAITING, DONE, or ERROR state.
    """
    if session.current_node is None:
        session.state = SessionState.DONE
        session.touch()
        return session

    node_id = session.current_node
    node = flow.nodes.get(node_id)
    if node is None:
        session.state = SessionState.ERROR
        session.error = f"Node {node_id!r} not found in flow {flow.id!r}"
        session.touch()
        return session

    session.steps_count += 1
    if session.steps_count > session.max_steps:
        session.state = SessionState.ERROR
        session.error = f"Max steps ({session.max_steps}) exceeded"
        session.touch()
        return session

    # 1. Resolve data_in
    data_in = resolver.resolve_data_in(node, session)

    # 2. Execute handler
    handler = registry.get(node.type)
    _started = time.monotonic()
    try:
        data_out: dict[str, Any] = await handler.execute(
            config=node.config,
            data_in=data_in,
            session=session,
            node=node,
        )
    except Exception as exc:
        logger.exception("Handler %s raised an error", node.type)
        session.state = SessionState.ERROR
        session.error = str(exc)
        next_node = _find_error_goto(node, flow)
        if next_node:
            session.state = SessionState.RUNNING
            session.current_node = next_node
            session.touch()
            return await run_step(session, flow, flow_loader)
        session.touch()
        return session

    metrics.record_node(node.type.value, time.monotonic() - _started)

    # 3. Save output + optional output_var
    session.node_outputs[node.id] = data_out
    output_var = node.config.get("output_var")
    if output_var:
        session.variables[output_var] = data_out

    # 4. Waiting nodes pause the loop
    if node.type in WAITING_NODES and data_out.get("__waiting__"):
        session.state = SessionState.WAITING
        session.touch()
        return session

    # 5. Subgraph: redirect to another flow
    subflow_id = data_out.get("__subgraph_flow_id__")
    if subflow_id:
        return await _enter_subgraph(session, flow, node, data_out, subflow_id, flow_loader)

    # 6. Loop: run body for each item, collect results
    if "__loop_items__" in data_out and data_out.get("__loop_body__"):
        return await _run_loop(session, flow, node, data_out, flow_loader)

    # 7. Resolve next node
    next_node = resolver.resolve_exec_out(node, data_out, session)

    # 8. END node: pop call stack (subgraph return)
    if node.type == NodeType.END and session.call_stack:
        return await _pop_call_stack(session, flow, flow_loader)

    # 9. Advance or finish
    if next_node:
        session.current_node = next_node
        session.state = SessionState.RUNNING
    elif session.call_stack:
        return await _pop_call_stack(session, flow, flow_loader)
    else:
        session.state = SessionState.DONE
        session.current_node = None

    session.touch()

    if session.state == SessionState.RUNNING:
        return await run_step(session, flow, flow_loader)

    return session


async def _enter_subgraph(
    session: Session,
    parent_flow: Flow,
    node: Any,
    data_out: dict[str, Any],
    subflow_id: str,
    flow_loader: FlowLoader | None,
) -> Session:
    if flow_loader is None:
        session.state = SessionState.ERROR
        session.error = "flow_loader is required for subgraph nodes"
        session.touch()
        return session

    subflow = await flow_loader(subflow_id)
    if subflow is None:
        session.state = SessionState.ERROR
        session.error = f"Subflow {subflow_id!r} not found"
        session.touch()
        return session

    # Push return frame: "parent_flow_id|return_node_id"
    return_node = resolver.resolve_exec_out(node, data_out, session)
    if return_node:
        session.call_stack.append(f"{parent_flow.id}|{return_node}")
    else:
        session.call_stack.append(f"{parent_flow.id}|__end__")

    session.current_node = subflow.start_node
    session.state = SessionState.RUNNING
    session.touch()
    return await run_step(session, subflow, flow_loader)


async def _pop_call_stack(
    session: Session,
    current_flow: Flow,
    flow_loader: FlowLoader | None,
) -> Session:
    frame = session.call_stack.pop()

    if "|" in frame:
        parent_flow_id, return_node = frame.split("|", 1)

        if return_node == "__end__" or not return_node:
            if session.call_stack:
                return await _pop_call_stack(session, current_flow, flow_loader)
            session.state = SessionState.DONE
            session.current_node = None
            session.touch()
            return session

        if parent_flow_id == current_flow.id:
            session.current_node = return_node
            session.state = SessionState.RUNNING
            session.touch()
            return await run_step(session, current_flow, flow_loader)

        if flow_loader is None:
            session.state = SessionState.ERROR
            session.error = f"Cannot return to flow {parent_flow_id!r}: no flow_loader"
            session.touch()
            return session

        parent_flow = await flow_loader(parent_flow_id)
        if parent_flow is None:
            session.state = SessionState.ERROR
            session.error = f"Parent flow {parent_flow_id!r} not found"
            session.touch()
            return session

        session.current_node = return_node
        session.state = SessionState.RUNNING
        session.touch()
        return await run_step(session, parent_flow, flow_loader)

    # Legacy: bare node_id in same flow
    session.current_node = frame
    session.state = SessionState.RUNNING
    session.touch()
    return await run_step(session, current_flow, flow_loader)


async def _run_loop(
    session: Session,
    flow: Flow,
    loop_node: Any,
    data_out: dict[str, Any],
    flow_loader: FlowLoader | None,
) -> Session:
    items: list[Any] = data_out["__loop_items__"]
    body_node_id: str = data_out["__loop_body__"]
    item_var: str = data_out.get("__loop_item_var__", "item")

    results: list[Any] = []

    if body_node_id in flow.nodes:
        for item in items:
            # Isolated sub-session per iteration
            sub = Session(
                flow_id=session.flow_id,
                variables=deepcopy(session.variables),
                node_outputs={},
                call_stack=[],
                max_steps=50,
            )
            sub.variables[item_var] = item
            sub.current_node = body_node_id
            sub.state = SessionState.RUNNING

            sub = await run_step(sub, flow, flow_loader)
            results.append(sub.node_outputs.get(body_node_id, {}))

    # Write results back to the loop node output in the parent session
    session.node_outputs[loop_node.id]["results"] = results
    session.node_outputs[loop_node.id]["count"] = len(results)
    output_var = loop_node.config.get("output_var")
    if output_var:
        session.variables[output_var] = {"results": results, "count": len(results)}

    # Continue after loop node
    next_node = resolver.resolve_exec_out(loop_node, data_out, session)
    if next_node:
        session.current_node = next_node
        session.state = SessionState.RUNNING
        session.touch()
        return await run_step(session, flow, flow_loader)

    if session.call_stack:
        return await _pop_call_stack(session, flow, flow_loader)

    session.state = SessionState.DONE
    session.current_node = None
    session.touch()
    return session


def _find_error_goto(node: Any, flow: Flow) -> str | None:
    for cond in node.exec_out.conditions:
        if cond.if_ in ("$error", "error") and cond.goto in flow.nodes:
            return cond.goto
    return None


# ─── Public entry points ──────────────────────────────────────────────────────

async def start_flow(
    session: Session,
    flow: Flow,
    flow_loader: FlowLoader | None = None,
) -> Session:
    if flow.start_node is None:
        session.state = SessionState.ERROR
        session.error = "Flow has no start_node"
        return session

    session.state = SessionState.RUNNING
    session.current_node = flow.start_node
    session.steps_count = 0
    session.touch()
    return await run_step(session, flow, flow_loader)


async def resume_flow(
    session: Session,
    flow: Flow,
    user_message: str,
    flow_loader: FlowLoader | None = None,
) -> Session:
    if session.state != SessionState.WAITING:
        raise ValueError(f"Cannot resume session in state {session.state!r}")

    session.variables["__pending_input__"] = user_message
    session.state = SessionState.RUNNING
    session.touch()
    return await run_step(session, flow, flow_loader)
