from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_key, WorkspaceDep
from api.deps import BotStoreDep
from config import settings
from stores.bot_store import BotConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bots", tags=["bots"], dependencies=[Depends(require_api_key)])

# Placeholder default — until a real public base_url is set we can't register
# a Telegram webhook, so we skip the call (e.g. in dev/tests).
_PLACEHOLDER_HOST = "yourdomain.com"


class BotCreate(BaseModel):
    name: str
    flow_id: str
    channel: str
    token: str = ""
    webhook_secret: str = ""
    project_id: str = ""


class BotResponse(BaseModel):
    id: str
    name: str
    flow_id: str
    channel: str
    token: str
    webhook_url: str
    project_id: str = ""


def _webhook_url(bot: BotConfig, base_url: str) -> str:
    return (
        f"{base_url}/webhook/telegram/{bot.token}"
        if bot.channel == "telegram"
        else f"{base_url}/webhook/generic/{bot.id}"
    )


async def _sync_telegram_webhook(bot: BotConfig, *, register: bool) -> None:
    """
    Best-effort Telegram setWebhook/deleteWebhook. Non-fatal: a failure here
    must not break bot CRUD. Skipped when no real public base_url is configured.
    """
    if bot.channel != "telegram" or not bot.token:
        return
    if not settings.base_url or _PLACEHOLDER_HOST in settings.base_url:
        logger.info("Skipping Telegram webhook sync — base_url not configured")
        return

    from adapters.telegram import TelegramAdapter

    adapter = TelegramAdapter()
    try:
        if register:
            await adapter.set_webhook(
                bot.token, _webhook_url(bot, settings.base_url), bot.webhook_secret
            )
            logger.info("Registered Telegram webhook for bot %s", bot.id)
        else:
            await adapter.delete_webhook(bot.token)
            logger.info("Removed Telegram webhook for bot %s", bot.id)
    except Exception as exc:  # noqa: BLE001 — best-effort, never fatal
        logger.warning("Telegram webhook sync failed for bot %s: %s", bot.id, exc)


def _to_response(bot: BotConfig, base_url: str) -> BotResponse:
    webhook_url = _webhook_url(bot, base_url)
    return BotResponse(
        id=bot.id,
        name=bot.name,
        flow_id=bot.flow_id,
        channel=bot.channel,
        token=bot.token,
        webhook_url=webhook_url,
        project_id=bot.project_id,
    )


@router.post("", response_model=BotResponse, status_code=201)
async def create_bot(body: BotCreate, bots: BotStoreDep, workspace: WorkspaceDep) -> BotResponse:
    import uuid
    bot = BotConfig(
        id=str(uuid.uuid4()),
        name=body.name,
        flow_id=body.flow_id,
        channel=body.channel,
        token=body.token,
        webhook_secret=body.webhook_secret,
        workspace_id=workspace,
        project_id=body.project_id,
    )
    await bots.save(bot)
    await _sync_telegram_webhook(bot, register=True)
    return _to_response(bot, settings.base_url)


@router.get("", response_model=list[BotResponse])
async def list_bots(
    bots: BotStoreDep, workspace: WorkspaceDep, project_id: str | None = None
) -> list[BotResponse]:
    all_bots = await bots.list_all(workspace_id=workspace, project_id=project_id)
    return [_to_response(b, settings.base_url) for b in all_bots]


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: str, bots: BotStoreDep, workspace: WorkspaceDep) -> BotResponse:
    bot = await bots.get_by_id(bot_id, workspace_id=workspace)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return _to_response(bot, settings.base_url)


@router.delete("/{bot_id}", status_code=204)
async def delete_bot(bot_id: str, bots: BotStoreDep, workspace: WorkspaceDep) -> None:
    bot = await bots.get_by_id(bot_id, workspace_id=workspace)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    await _sync_telegram_webhook(bot, register=False)
    await bots.delete(bot_id, workspace_id=workspace)
