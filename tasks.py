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

    loader = make_flow_loader(flow_store)
    try:
        if session_id:
            session = await session_store.get(session_id)
            if session is None:
                logger.warning("run_flow_task: session %s not found", session_id)
                return
            if session.state != SessionState.WAITING:
                logger.warning("run_flow_task: session %s is not waiting (%s)", session_id, session.state)
                return
            session = await resume_flow(session, flow, user_text, flow_loader=loader)
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
