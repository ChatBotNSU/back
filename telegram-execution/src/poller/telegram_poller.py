import logging
import threading
import asyncio
from typing import Dict, Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from sender.telegram_sender import TelegramResponseSender
from controller.redis_streams import RedisStreamsController
from models.redis_io_streams import ExecutionRequest

logger = logging.getLogger("app")

class TelegramPoller:
    _instance: Optional["TelegramPoller"] = None
    _lock = threading.Lock()
    _bots: Dict[str, int] = {}

    def __init__(self):
        self.sender = TelegramResponseSender.get_instance()
        self.controller = RedisStreamsController.get_instance()
        TelegramPoller._instance = self
        logger.info("TelegramPoller initialized")
    
    @staticmethod
    def get_instance() -> "TelegramPoller":
        if TelegramPoller._instance is None:
            raise RuntimeError("TelegramPoller not initialized yet. Expected call of constructor beforehand.")
        return TelegramPoller._instance
    
    async def update_bots(self, token: str, chatbot_id: int):
        async with self._lock:
            if token not in self._bots:
                self._poll_bot(token)
            self._bots[token] = chatbot_id

    async def _poll_bot(self, token: str, chatbot_id: int):
        try:
            bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            
            dp = Dispatcher()
            self._setup_handlers(dp, chatbot_id)
            
            task = asyncio.create_task(
                self._poll_bot_updates(bot, dp, token)
            )
            
            logger.info(f"Bot {chatbot_id} polling started")
            
        except Exception as e:
            logger.error(f"Failed to start bot {chatbot_id}: {e}")

    def _setup_handlers(self, dispatcher: Dispatcher, bot_id: str):
        @dispatcher.message()
        async def handle_message(message):
            try:
                execution_id = message.chat.id + "_telegram"

                request = ExecutionRequest(
                    execution_id=execution_id,
                    chatbot_id=bot_id,
                    message=message.text 
                )
                future = await self.sender.add_future(execution_id)
                await self.controller.put_message(request)
                
                logger.info(f"Message from user {message.from_user.id} sent to Redis, execution_id={execution_id}")
                
                result = await asyncio.wait_for(future)
                await message.answer(result)
                
            except Exception as e:
                logger.error(f"Error handling message in bot {bot_id}: {e}")
                await message.answer("⚠️ Произошла ошибка. Попробуйте позже.")

    async def _poll_bot_updates(self, bot: Bot, dispatcher: Dispatcher, token: str):
        
        try:
            await dispatcher.start_polling(
                bot,
                allowed_updates=dispatcher.resolve_used_update_types(),
                polling_timeout=10
            )
        except asyncio.CancelledError:
            logger.info(f"Polling for bot {token} cancelled")
        except Exception as e:
            logger.error(f"Polling error for bot {token}: {e}")
        finally:
            if token in self._bots:
                del self._bots[token]