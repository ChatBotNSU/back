from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_key, WorkspaceDep

from api.deps import FlowStoreDep, SessionStoreDep
from engine.loader import make_flow_loader
from engine.runner import resume_flow
from models.session import Session, SessionState

router = APIRouter(prefix="/api/sessions", tags=["sessions"], dependencies=[Depends(require_api_key)])


# ─── Response schemas ─────────────────────────────────────────────────────────

class SessionDetail(BaseModel):
    id: str
    flow_id: str
    bot_id: str
    channel: str
    user_id: str
    state: SessionState
    current_node: str | None
    variables: dict[str, Any]
    node_outputs: dict[str, dict[str, Any]]
    call_stack: list[str]
    steps_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class SessionSummary(BaseModel):
    id: str
    flow_id: str
    state: SessionState
    current_node: str | None
    steps_count: int
    updated_at: datetime


class ResumeRequest(BaseModel):
    message: str


# ─── Routes ───────────────────────────────────────────────────────────────────

def _check_ws(session: Session | None, workspace: str) -> Session:
    if session is None or session.workspace_id != workspace:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str, sessions: SessionStoreDep, workspace: WorkspaceDep
) -> SessionDetail:
    session = _check_ws(await sessions.get(session_id), workspace)
    return _to_detail(session)


@router.get("/{session_id}/trace")
async def get_session_trace(
    session_id: str, sessions: SessionStoreDep, workspace: WorkspaceDep
) -> dict[str, Any]:
    """Return node_outputs in execution order for the debugger panel."""
    session = _check_ws(await sessions.get(session_id), workspace)
    return {
        "session_id": session_id,
        "state": session.state,
        "steps_count": session.steps_count,
        "trace": [
            {"node_id": node_id, "output": output}
            for node_id, output in session.node_outputs.items()
        ],
    }


@router.post("/{session_id}/resume", response_model=SessionDetail)
async def resume_session(
    session_id: str,
    body: ResumeRequest,
    sessions: SessionStoreDep,
    flows: FlowStoreDep,
    workspace: WorkspaceDep,
) -> SessionDetail:
    """
    Manually inject a user message into a WAITING session.
    Used by the debugger and direct API integrations.
    """
    session = _check_ws(await sessions.get(session_id), workspace)
    if session.state != SessionState.WAITING:
        raise HTTPException(
            status_code=409,
            detail=f"Session is not waiting (state={session.state})",
        )

    flow = await flows.get(session.flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    session = await resume_flow(session, flow, body.message, flow_loader=make_flow_loader(flows))
    await sessions.save(session)
    return _to_detail(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str, sessions: SessionStoreDep, workspace: WorkspaceDep
) -> None:
    _check_ws(await sessions.get(session_id), workspace)
    await sessions.delete(session_id)


@router.get("", response_model=list[SessionSummary])
async def list_sessions_by_flow(
    flow_id: str, sessions: SessionStoreDep, workspace: WorkspaceDep
) -> list[SessionSummary]:
    """List sessions for a given flow_id (query param), scoped to the workspace."""
    all_sessions = [
        s for s in await sessions.list_by_flow(flow_id)
        if s.workspace_id == workspace
    ]
    return [
        SessionSummary(
            id=s.id,
            flow_id=s.flow_id,
            state=s.state,
            current_node=s.current_node,
            steps_count=s.steps_count,
            updated_at=s.updated_at,
        )
        for s in all_sessions
    ]


# ─── Helper ───────────────────────────────────────────────────────────────────

def _to_detail(session: Session) -> SessionDetail:
    return SessionDetail(
        id=session.id,
        flow_id=session.flow_id,
        bot_id=session.bot_id,
        channel=session.channel,
        user_id=session.user_id,
        state=session.state,
        current_node=session.current_node,
        variables=session.variables,
        node_outputs=session.node_outputs,
        call_stack=session.call_stack,
        steps_count=session.steps_count,
        error=session.error,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )
