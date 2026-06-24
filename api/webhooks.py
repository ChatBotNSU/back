from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from adapters import inbound
from api.deps import ArqPoolDep, BotStoreDep, DeadLetterStoreDep, FlowStoreDep, SessionStoreDep
from api.ratelimit import RedisRateLimiter, SlidingWindowRateLimiter
from config import settings
from engine.loader import make_flow_loader
from engine.registry import load_all_handlers
from engine.runner import start_flow, resume_flow
from models.session import Session, SessionState
from services import metrics
from stores.bot_store import BotConfig
from stores.dead_letter import DeadLetterEntry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhooks"])

load_all_handlers()

# Per-key (bot/session) inbound rate limiter. Swapped for a Redis-backed one
# at startup when Redis is available (see set_rate_limiter / main.lifespan).
_rate_limiter: SlidingWindowRateLimiter | RedisRateLimiter = SlidingWindowRateLimiter(
    settings.webhook_rate_limit, settings.webhook_rate_window
)


def set_rate_limiter(limiter: SlidingWindowRateLimiter | RedisRateLimiter) -> None:
    global _rate_limiter
    _rate_limiter = limiter


async def _enforce_rate_limit(key: str) -> None:
    if not await _rate_limiter.allow_async(key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


async def _dispatch_run(
    arq_pool: Any,
    background: BackgroundTasks,
    *,
    existing: "Session | None",
    flow_id: str,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    dlq: DeadLetterStoreDep,
    init_vars: dict[str, Any],
    user_text: str,
) -> None:
    """Run a flow via the ARQ queue when available, else inline BackgroundTasks."""
    if arq_pool is not None:
        session_id = existing.id if (existing and existing.state == SessionState.WAITING) else None
        await arq_pool.enqueue_job(
            "run_flow_task", session_id=session_id, flow_id=flow_id,
            init_vars=init_vars, user_text=user_text,
        )
    else:
        background.add_task(
            _run_flow_bg, existing, flow_id, flows, sessions, dlq, init_vars, user_text,
        )


def _verify_telegram_secret(request: Request, bot: BotConfig) -> None:
    """Validate Telegram's X-Telegram-Bot-Api-Secret-Token header."""
    if not bot.webhook_secret:
        return  # no secret configured → skip (back-compat)
    presented = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(presented, bot.webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")


def _verify_generic_signature(request: Request, bot: BotConfig, raw_body: bytes) -> None:
    """Validate an HMAC-SHA256 signature over the raw body (X-Signature header)."""
    if not bot.webhook_secret:
        return  # no secret configured → skip (back-compat)
    presented = request.headers.get("X-Signature", "")
    expected = hmac.new(bot.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")


# ─── Telegram ─────────────────────────────────────────────────────────────────

@router.post("/telegram/{bot_token}")
async def telegram_webhook(
    bot_token: str,
    payload: dict[str, Any],
    background: BackgroundTasks,
    request: Request,
    bots: BotStoreDep,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    dlq: DeadLetterStoreDep,
    arq: ArqPoolDep,
) -> dict[str, str]:
    await _enforce_rate_limit(f"tg:{bot_token}")
    metrics.record_webhook("telegram")
    bot = await bots.get_by_token(bot_token)
    if bot is None:
        logger.warning("Unknown telegram bot token")
        return {"ok": "true"}

    _verify_telegram_secret(request, bot)

    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return {"ok": "true"}

    tg_user = message.get("from", {})
    user_id = str(tg_user.get("id", ""))
    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", user_id))
    session_key = f"{bot.id}:{chat_id}"

    existing = await _find_active_session(sessions, bot.flow_id, session_key)

    init_vars: dict[str, Any] = {
        "__session_key__": session_key,
        "__bot_token__": bot_token,
        "user_id": user_id,
        "chat_id": chat_id,
        "text": text,
        "channel": "telegram",
        "attachments": message.get("photo") or message.get("document") or [],
        "user_meta": {
            "first_name": tg_user.get("first_name", ""),
            "last_name": tg_user.get("last_name", ""),
            "username": tg_user.get("username", ""),
            "language_code": tg_user.get("language_code", ""),
        },
    }

    await _dispatch_run(
        arq, background, existing=existing, flow_id=bot.flow_id,
        flows=flows, sessions=sessions, dlq=dlq, init_vars=init_vars, user_text=text,
    )
    return {"ok": "true"}


# ─── Generic channel ──────────────────────────────────────────────────────────

@router.post("/generic/{bot_id}")
async def generic_webhook(
    bot_id: str,
    payload: dict[str, Any],
    background: BackgroundTasks,
    request: Request,
    bots: BotStoreDep,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    dlq: DeadLetterStoreDep,
    arq: ArqPoolDep,
) -> dict[str, str]:
    await _enforce_rate_limit(f"generic:{bot_id}")
    metrics.record_webhook("generic")
    bot = await bots.get_by_id(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    _verify_generic_signature(request, bot, await request.body())

    user_id = str(payload.get("user_id", "anonymous"))
    session_key = f"{bot.id}:{user_id}"
    existing = await _find_active_session(sessions, bot.flow_id, session_key)

    init_vars: dict[str, Any] = {
        "__session_key__": session_key,
        "__bot_token__": bot.token,
        "user_id": user_id,
        "text": str(payload.get("text", "")),
        "channel": bot.channel,
        "payload": payload,
    }

    await _dispatch_run(
        arq, background, existing=existing, flow_id=bot.flow_id,
        flows=flows, sessions=sessions, dlq=dlq, init_vars=init_vars,
        user_text=str(payload.get("text", "")),
    )
    return {"ok": "true"}


# ─── External wait-event delivery ─────────────────────────────────────────────

@router.post("/event/{session_id}/{wait_key}")
async def deliver_wait_event(
    session_id: str,
    wait_key: str,
    payload: dict[str, Any],
    background: BackgroundTasks,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    dlq: DeadLetterStoreDep,
) -> dict[str, str]:
    await _enforce_rate_limit(f"event:{session_id}")
    session = await sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.state != SessionState.WAITING:
        raise HTTPException(status_code=409, detail=f"Session is not waiting (state={session.state})")

    waiting_node = session.variables.get("__waiting_node__")
    session.variables[f"__wait_event_{waiting_node}__"] = payload
    background.add_task(_resume_bg, session, flows, sessions, dlq, "")
    return {"ok": "true"}


# ─── WhatsApp / VK / Viber (normalized inbound) ───────────────────────────────

def _channel_ack(channel: str) -> Any:
    # VK requires the literal "ok"; others accept JSON 200.
    return PlainTextResponse("ok") if channel == "vk" else {"ok": "true"}


@router.get("/{channel}/{bot_id}")
async def channel_verify(channel: str, bot_id: str, request: Request, bots: BotStoreDep) -> Any:
    """WhatsApp Cloud API webhook verification handshake (hub.challenge)."""
    bot = await bots.get_by_id(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    if channel == "whatsapp":
        params = request.query_params
        if (
            params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == bot.metadata.get("verify_token")
        ):
            return PlainTextResponse(params.get("hub.challenge", ""))
        raise HTTPException(status_code=403, detail="Verification failed")
    raise HTTPException(status_code=404, detail="Not found")


@router.post("/{channel}/{bot_id}")
async def channel_webhook(
    channel: str,
    bot_id: str,
    payload: dict[str, Any],
    background: BackgroundTasks,
    bots: BotStoreDep,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    dlq: DeadLetterStoreDep,
    arq: ArqPoolDep,
) -> Any:
    await _enforce_rate_limit(f"{channel}:{bot_id}")
    metrics.record_webhook(channel)
    if not inbound.supported(channel):
        raise HTTPException(status_code=404, detail="Unsupported channel")
    bot = await bots.get_by_id(bot_id)
    if bot is None or bot.channel != channel:
        raise HTTPException(status_code=404, detail="Bot not found")

    # VK Callback API handshakes.
    if channel == "vk":
        if payload.get("type") == "confirmation":
            return PlainTextResponse(bot.metadata.get("vk_confirmation", ""))
        if bot.webhook_secret and payload.get("secret") != bot.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid secret")

    parsed = inbound.parse(channel, payload)
    if parsed is None:
        return _channel_ack(channel)

    session_key = f"{bot.id}:{parsed['chat_id']}"
    existing = await _find_active_session(sessions, bot.flow_id, session_key)
    init_vars: dict[str, Any] = {
        "__session_key__": session_key,
        "__bot_token__": bot.token,
        "user_id": parsed["user_id"],
        "chat_id": parsed["chat_id"],
        "text": parsed["text"],
        "channel": channel,
        "attachments": parsed["attachments"],
        "user_meta": parsed["user_meta"],
    }
    await _dispatch_run(
        arq, background, existing=existing, flow_id=bot.flow_id,
        flows=flows, sessions=sessions, dlq=dlq, init_vars=init_vars, user_text=parsed["text"],
    )
    return _channel_ack(channel)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _find_active_session(
    sessions: SessionStoreDep,
    flow_id: str,
    session_key: str,
) -> Session | None:
    s = await sessions.get_by_key(session_key)
    if s and s.flow_id == flow_id and s.state in (SessionState.WAITING, SessionState.IDLE):
        return s
    return None


async def _record_dead_letter(
    dlq: DeadLetterStoreDep,
    *,
    flow_id: str,
    session: Session | None,
    error: str,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        await dlq.push(
            DeadLetterEntry(
                flow_id=flow_id,
                session_id=session.id if session else None,
                error=error,
                kind=kind,
                payload=payload or {},
            )
        )
    except Exception:  # noqa: BLE001 — DLQ must never break the request path
        logger.exception("Failed to write dead-letter entry")


async def _run_flow_bg(
    existing: Session | None,
    flow_id: str,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    dlq: DeadLetterStoreDep,
    init_vars: dict[str, Any],
    user_text: str,
) -> None:
    flow = await flows.get(flow_id)
    if flow is None:
        logger.error("Flow %s not found", flow_id)
        await _record_dead_letter(
            dlq, flow_id=flow_id, session=None,
            error="Flow not found", kind="flow_error",
            payload={"init_vars": init_vars, "user_text": user_text},
        )
        return

    # A configured `/command` trigger always wins: it interrupts any ongoing
    # WAITING session and re-enters the flow from that trigger node. Lets one
    # flow expose several entry points (e.g. /start, /help, /revenue).
    from handlers.message_trigger import find_command_match
    trigger_node = find_command_match(flow, user_text)

    loader = make_flow_loader(flows)
    try:
        if trigger_node is not None:
            session = Session(
                flow_id=flow_id, workspace_id=flow.workspace_id, project_id=flow.project_id
            )
            if existing is not None:
                # Preserve session_id so the bot:chat mapping stays stable.
                session.id = existing.id
                # Carry user-collected variables across the command boundary so
                # /revenue can still see {name}, {currency}, etc. set during
                # /start. Drop runtime-control and per-node state (starts with __).
                session.variables.update({
                    k: v for k, v in existing.variables.items() if not k.startswith("__")
                })
                # Keep the running message log so Demo's incremental render
                # stays in sync; production adapters fire on append, not replay.
                if "__messages__" in existing.variables:
                    session.variables["__messages__"] = list(existing.variables["__messages__"])
            session.variables.update(init_vars)
            session = await start_flow(
                session, flow, flow_loader=loader, entry_node=trigger_node.id
            )
        elif existing and existing.state == SessionState.WAITING:
            session = await resume_flow(existing, flow, user_text, flow_loader=loader)
        else:
            session = Session(
                flow_id=flow_id, workspace_id=flow.workspace_id, project_id=flow.project_id
            )
            session.variables.update(init_vars)
            session = await start_flow(session, flow, flow_loader=loader)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Flow %s crashed", flow_id)
        await _record_dead_letter(
            dlq, flow_id=flow_id, session=existing,
            error=str(exc), kind="exception",
            payload={"user_text": user_text},
        )
        return

    await sessions.save(session)
    await _persist_shared_vars(flows, flow, session)
    metrics.record_flow(session.state.value)
    if session.state == SessionState.ERROR:
        await _record_dead_letter(
            dlq, flow_id=flow_id, session=session,
            error=session.error or "unknown", kind="flow_error",
        )


async def _persist_shared_vars(
    flows: FlowStoreDep, flow: Any, session: Session
) -> None:
    """Copy user-collected variables from a finished session into
    flow.metadata['__shared_vars__'] so future cron / fresh-command sessions
    can preload them. Skipped while the session is still WAITING — partial
    state would leak half-collected slots into the global pool.
    """
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
            return  # nothing actually changed
        flow.metadata["__shared_vars__"] = merged
        await flows.save(flow)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to persist shared vars for flow %s", flow.id, exc_info=True)


async def _resume_bg(
    session: Session,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    dlq: DeadLetterStoreDep,
    user_text: str,
) -> None:
    flow = await flows.get(session.flow_id)
    if flow is None:
        return
    try:
        session = await resume_flow(session, flow, user_text, flow_loader=make_flow_loader(flows))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Resume of flow %s crashed", session.flow_id)
        await _record_dead_letter(
            dlq, flow_id=session.flow_id, session=session,
            error=str(exc), kind="exception",
        )
        return
    await sessions.save(session)
    metrics.record_flow(session.state.value)
    if session.state == SessionState.ERROR:
        await _record_dead_letter(
            dlq, flow_id=session.flow_id, session=session,
            error=session.error or "unknown", kind="flow_error",
        )
