import logging
import asyncio
from typing import Dict, Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import HTTPException

from sender.telegram_sender import TelegramResponseSender
from controller.redis_streams import RedisStreamsController
from models.redis_io_streams import ExecutionRequest
from models.message import InMessage

logger = logging.getLogger("app")

class TelegramPoller:
    _instance: Optional["TelegramPoller"] = None
    _lock = asyncio.Lock()
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
                self._bots[token] = chatbot_id
                await self._poll_bot(token)
            self._bots[token] = chatbot_id

    async def get_all(self) -> Dict[str, int]:
        async with self._lock:
            return self._bots

    async def get_by_token(self, token: str) -> int:
        async with self._lock:
            if token not in self._bots:
                raise HTTPException(status_code=404, detail="Token not found")
            return self._bots[token]

    async def _poll_bot(self, token: str):
        try:
            bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            
            dp = Dispatcher()
            self._setup_handlers(dp, token)
            
            asyncio.create_task(
                self._poll_bot_updates(bot, dp, token)
            )
            
            logger.info(f"Bot {token} polling started")
            
        except Exception as e:
            logger.error(f"Failed to start bot {token}: {e}")

    def _setup_handlers(self, dispatcher: Dispatcher, token:str):
        @dispatcher.callback_query()
        async def handle_callback(callback_query: CallbackQuery):
            try:
                # Достаём текст нажатой кнопки из reply_markup
                chosen_text = None
                if callback_query.message.reply_markup:
                    for row in callback_query.message.reply_markup.inline_keyboard:
                        for button in row:
                            if button.callback_data == callback_query.data:
                                chosen_text = button.text
                                break
                        if chosen_text:
                            break
                        
                if not chosen_text:
                    await callback_query.answer("Ошибка: кнопка не найдена")
                    return

                await callback_query.answer()  # убираем "часики" в интерфейсе

                execution_id = callback_query.message.chat.id
                async with self._lock:
                    bot_id = self._bots[token]

                in_message = InMessage(text=chosen_text, restart_command=False)
                request = ExecutionRequest(
                    execution_id=execution_id,
                    chatbot_id=bot_id,
                    message=in_message
                )

                future = await self.sender.add_future(execution_id)
                await self.controller.put_message(request)

                # Ожидаем ответ и отправляем его новым сообщением
                out_message = await asyncio.wait_for(future, timeout=None)

                bot = callback_query.bot  # экземпляр бота из контекста
                await bot.send_message(chat_id=execution_id, text=out_message.text)

                # Дополнительно прикрепляем медиа из ответа
                for image_url in out_message.images or []:
                    try:
                        await bot.send_photo(execution_id, image_url)
                    except Exception as e:
                        logger.error(f"Error sending image: {e}")
                for audio_url in out_message.audios or []:
                    try:
                        await bot.send_audio(execution_id, audio_url)
                    except Exception as e:
                        logger.error(f"Error sending audio: {e}")
                for file_url in out_message.files or []:
                    try:
                        await bot.send_document(execution_id, file_url)
                    except Exception as e:
                        logger.error(f"Error sending file: {e}")

                # Если ответ опять содержит варианты выбора – отправить клавиатуру
                if out_message.choise_options:
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text=opt, callback_data=f"choice_{i}")]
                            for i, opt in enumerate(out_message.choise_options)
                        ]
                    )
                    await bot.send_message(
                        execution_id,
                        "Выберите вариант:",
                        reply_markup=keyboard
                    )

            except Exception as e:
                logger.error(f"Error handling callback in bot {token}: {e}")
                try:
                    await callback_query.answer("⚠️ Произошла ошибка.")
                except Exception:
                    pass
        @dispatcher.message()
        async def handle_message(message):
            try:
                execution_id = message.chat.id 

                # Внутри handle_message, замените текущий блок формирования InMessage на:
                images = []
                if message.photo:
                    largest_photo = message.photo[-1]
                    images.append(largest_photo.file_id)
                
                audios = []
                if message.voice:
                    audios.append(message.voice.file_id)
                if message.audio:
                    audios.append(message.audio.file_id)
                
                files = []
                if message.document:
                    files.append(message.document.file_id)
                
                in_message = InMessage(
                    text=message.caption or message.text,
                    images=images if images else None,
                    audios=audios if audios else None,
                    files=files if files else None,
                    restart_command=False
                )
                async with self._lock:
                    bot_id = self._bots[token]

                request = ExecutionRequest(
                    execution_id=execution_id,
                    chatbot_id= bot_id,
                    message=in_message
                )
                future = await self.sender.add_future(execution_id)
                await self.controller.put_message(request)
                
                logger.info(f"Message from user {message.from_user.id} sent to Redis, execution_id={execution_id}")
                
                out_message = await asyncio.wait_for(future, timeout=None)
                await message.answer(out_message.text)

                for image_url in out_message.images:
                    try:
                        await message.answer_photo(image_url)
                    except Exception as e:
                        logger.error(f"Error sending image: {e}")

                for audio_url in out_message.audios:
                    try:
                        await message.answer_audio(audio_url)
                    except Exception as e:
                        logger.error(f"Error sending audio: {e}")

                for file_url in out_message.files:
                    try:
                        await message.answer_document(file_url)
                    except Exception as e:
                        logger.error(f"Error sending file: {e}")
            
                if out_message.choise_options:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text=option, callback_data=f"choice_{i}")]
                            for i, option in enumerate(out_message.choise_options)
                        ]
                    )
                    await message.answer("Выберите вариант:", reply_markup=keyboard)
                
            except Exception as e:
                logger.error(f"Error handling message in bot {token}: {e}")
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