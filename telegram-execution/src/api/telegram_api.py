import logging
import asyncio
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from poller.telegram_poller import TelegramPoller


logger = logging.getLogger("app")

router = APIRouter()

poller = TelegramPoller()

@router.post("/assigne")
async def assigne(token: str, chatbot_id: int):
    await poller.update_bots(token, chatbot_id)