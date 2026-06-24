from __future__ import annotations

import logging
import re
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
    NodeType.AGENT,
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

    # 4a. Halt sentinel — any handler may return __halt__ to end the session
    # immediately (e.g. message_trigger when the command doesn't match).
    if data_out.get("__halt__"):
        session.state = SessionState.DONE
        session.current_node = None
        session.touch()
        return session

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


# Variables auto-forwarded into an isolated subflow scope. These are the
# transport-level fields a child flow needs to send messages back to the user
# and resume correctly across webhook calls — never the parent's business data.
_SYSTEM_VARS = {
    "channel", "chat_id", "user_id", "__bot_token__", "__session_key__",
    "text", "attachments", "user_meta",
}


def _is_isolated_subgraph(node: Any) -> bool:
    cfg = node.config
    if cfg.get("isolated"):
        return True
    if cfg.get("input_mapping"):
        return True
    if cfg.get("output_mapping"):
        return True
    return False


def _render_template(value: Any, variables: dict[str, Any]) -> Any:
    """Render a `{{var}}` template against parent variables.

    - A string that is *exactly* `{{name}}` returns the raw value (preserves
      type — dict/list/number/bool round-trip without stringification).
    - A string with embedded templates is rendered field-by-field as text.
    - Non-strings are returned as-is (literal config values).
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith("{{") and stripped.endswith("}}") and "{{" not in stripped[2:-2]:
        key = stripped[2:-2].strip()
        return _nested_lookup(key, variables)
    def replacer(match: "re.Match[str]") -> str:
        key = match.group(1).strip()
        val = _nested_lookup(key, variables)
        return str(val) if val is not None else match.group(0)
    return re.sub(r"\{\{(.+?)\}\}", replacer, value)


def _nested_lookup(key: str, variables: dict[str, Any]) -> Any:
    cur: Any = variables
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


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

    # Set up variable scope. In isolated mode the parent's vars are snapshot
    # and replaced with a fresh dict built from system passthroughs + mapped
    # inputs. Legacy mode keeps the shared dict. var_stack stays aligned with
    # call_stack — None entries mark legacy frames.
    if _is_isolated_subgraph(node):
        parent_vars = deepcopy(session.variables)
        session.var_stack.append({
            "parent_vars": parent_vars,
            "output_mapping": dict(node.config.get("output_mapping") or {}),
        })

        child_vars: dict[str, Any] = {
            k: deepcopy(parent_vars[k]) for k in _SYSTEM_VARS if k in parent_vars
        }
        # __messages__ is shared by reference so messages sent from the subflow
        # land directly in the parent's outbox (consistent with shared mode).
        if "__messages__" in parent_vars:
            child_vars["__messages__"] = parent_vars["__messages__"]

        for input_name, template in (node.config.get("input_mapping") or {}).items():
            child_vars[input_name] = _render_template(template, parent_vars)

        session.variables = child_vars
    else:
        session.var_stack.append(None)

    session.current_node = subflow.start_node
    session.current_flow_id = subflow.id
    session.state = SessionState.RUNNING
    session.touch()
    return await run_step(session, subflow, flow_loader)


def _restore_parent_scope(session: Session) -> None:
    """Restore parent variables and apply output_mapping when returning from
    an isolated subgraph. Pops one entry from var_stack (kept in sync with
    call_stack). For legacy frames (None / missing) this is a no-op.
    """
    if not session.var_stack:
        return
    frame = session.var_stack.pop()
    if frame is None:
        return
    child_vars = session.variables
    parent_vars: dict[str, Any] = frame.get("parent_vars") or {}
    output_mapping: dict[str, str] = frame.get("output_mapping") or {}
    for child_name, parent_name in output_mapping.items():
        if not parent_name:
            continue
        parent_vars[parent_name] = child_vars.get(child_name)
    # Forward outbox to parent. At entry we aliased child_vars["__messages__"]
    # with parent_vars["__messages__"] (same list ref), so child always carries
    # the full parent prefix plus any messages queued inside the subflow.
    # A JSON save/load cycle in between WAITING + resume turns the alias into
    # two equal-but-separate lists, so extending here would double everything
    # that was already in parent at entry time. Replacing parent with a fresh
    # copy of child is correct in both cases.
    child_messages = child_vars.get("__messages__")
    if isinstance(child_messages, list):
        parent_vars["__messages__"] = list(child_messages)
    session.variables = parent_vars


async def _pop_call_stack(
    session: Session,
    current_flow: Flow,
    flow_loader: FlowLoader | None,
) -> Session:
    frame = session.call_stack.pop()
    _restore_parent_scope(session)

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
            session.current_flow_id = current_flow.id
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
        session.current_flow_id = parent_flow.id
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
    entry_node: str | None = None,
) -> Session:
    """Start a flow from `entry_node` (a trigger node id) or, when not given,
    from the flow's configured `start_node`. The trigger model lets one flow
    have several entry points — message commands and cron ticks each land on
    their own node and run their own branch."""
    target = entry_node or flow.start_node
    if target is None:
        session.state = SessionState.ERROR
        session.error = "Flow has no start_node"
        return session
    if target not in flow.nodes:
        session.state = SessionState.ERROR
        session.error = f"Entry node {target!r} not found in flow {flow.id!r}"
        return session

    session.state = SessionState.RUNNING
    session.current_node = target
    session.current_flow_id = flow.id
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

    # When the session paused inside a subgraph, the current node lives in a
    # *child* flow, not the root we were called with. Re-resolve the actual
    # flow via the loader so run_step sees the right `nodes` dict.
    target_flow = flow
    if (
        session.current_flow_id
        and session.current_flow_id != flow.id
        and flow_loader is not None
    ):
        loaded = await flow_loader(session.current_flow_id)
        if loaded is not None:
            target_flow = loaded

    session.variables["__pending_input__"] = user_message
    session.state = SessionState.RUNNING
    session.touch()
    return await run_step(session, target_flow, flow_loader)
