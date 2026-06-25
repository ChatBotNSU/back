"""
ARQ task definitions.

These functions are called by the ARQ worker. The `ctx` dict is populated
in worker.py's on_startup hook and contains shared resources (stores, etc.).

The same functions are called directly (without ARQ) when ARQ is unavailable,
by passing a minimal ctx dict constructed in api/webhooks.py.
"""
from __future__ import annotations

import logging
from typing import Any

from engine.loader import make_flow_loader
from engine.runner import start_flow, resume_flow
from models.session import Session, SessionState
from services import metrics
from stores.dead_letter import DeadLetterEntry

logger = logging.getLogger(__name__)


async def _to_dead_letter(ctx: dict[str, Any], entry: DeadLetterEntry) -> None:
    dlq = ctx.get("dead_letter")
    if dlq is None:
        return
    try:
        await dlq.push(entry)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to write dead-letter entry")


async def _persist_shared_vars(flow_store: Any, flow: Any, session: Session) -> None:
    """Copy user-collected vars from a finished session into
    flow.metadata['__shared_vars__'] so cron / fresh-command sessions can
    preload them. Mirror of api/webhooks._persist_shared_vars."""
    if session.state not in (SessionState.DONE, SessionState.ERROR):
        return
    new_shared = {
        k: v for k, v in session.variables.items()
        if not k.startswith("__") and k not in {"text", "channel", "chat_id", "user_id"}
    }
    if not new_shared:
        return
    try:
        existing = flow.metadata.get("__shared_vars__") or {}
        if not isinstance(existing, dict):
            existing = {}
        merged = {**existing, **new_shared}
        if merged == existing:
            return
        flow.metadata["__shared_vars__"] = merged
        await flow_store.save(flow)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to persist shared vars for flow %s", flow.id, exc_info=True)


async def run_flow_task(
    ctx: dict[str, Any],
    *,
    session_id: str | None,
    flow_id: str,
    init_vars: dict[str, Any],
    user_text: str,
) -> None:
    """
    Start a new flow session, or resume an existing WAITING one.
    Persists the updated session back to the store.

    On a raised exception the entry is recorded to the dead-letter store and
    re-raised so ARQ's retry policy still applies. Flows that finish in ERROR
    state are recorded without re-raising.
    """
    session_store = ctx["session_store"]
    flow_store = ctx["flow_store"]

    flow = await flow_store.get(flow_id)
    if flow is None:
        logger.error("run_flow_task: flow %s not found", flow_id)
        await _to_dead_letter(ctx, DeadLetterEntry(
            flow_id=flow_id, session_id=session_id, error="Flow not found",
            kind="flow_error", payload={"init_vars": init_vars, "user_text": user_text},
        ))
        return

    # A configured `/command` trigger wins: it interrupts any WAITING session and
    # re-enters the flow from that trigger node. Mirrors api/webhooks._run_flow_bg
    # so behaviour is identical whether a run is dispatched via ARQ or inline.
    from handlers.message_trigger import find_command_match
    trigger_node = find_command_match(flow, user_text)

    existing: Session | None = None
    if session_id:
        existing = await session_store.get(session_id)

    loader = make_flow_loader(flow_store)
    try:
        if trigger_node is not None:
            session = Session(
                flow_id=flow_id, workspace_id=flow.workspace_id, project_id=flow.project_id
            )
            if existing is not None:
                session.id = existing.id  # keep the bot:chat mapping stable
                session.variables.update({
                    k: v for k, v in existing.variables.items() if not k.startswith("__")
                })
                if "__messages__" in existing.variables:
                    session.variables["__messages__"] = list(existing.variables["__messages__"])
            session.variables.update(init_vars)
            session = await start_flow(
                session, flow, flow_loader=loader, entry_node=trigger_node.id
            )
        elif existing is not None:
            if existing.state != SessionState.WAITING:
                logger.warning("run_flow_task: session %s is not waiting (%s)", session_id, existing.state)
                return
            session = await resume_flow(existing, flow, user_text, flow_loader=loader)
        else:
            session = Session(
                flow_id=flow_id, workspace_id=flow.workspace_id, project_id=flow.project_id
            )
            session.variables.update(init_vars)
            session = await start_flow(session, flow, flow_loader=loader)
    except Exception as exc:
        logger.exception("run_flow_task: flow %s crashed", flow_id)
        await _to_dead_letter(ctx, DeadLetterEntry(
            flow_id=flow_id, session_id=session_id, error=str(exc),
            kind="exception", payload={"user_text": user_text},
        ))
        raise

    await session_store.save(session)
    await _persist_shared_vars(flow_store, flow, session)
    metrics.record_flow(session.state.value)
    if session.state == SessionState.ERROR:
        await _to_dead_letter(ctx, DeadLetterEntry(
            flow_id=flow_id, session_id=session.id,
            error=session.error or "unknown", kind="flow_error",
        ))
    logger.info(
        "run_flow_task done: session=%s state=%s steps=%d",
        session.id, session.state, session.steps_count,
    )
