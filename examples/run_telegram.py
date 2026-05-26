"""Прогнать пример через живой Telegram-поллинг — без Redis/MinIO/docker.

aiogram-поллер крутится в одном процессе и зовёт Engine.execute напрямую.
Каждому TG-чату даётся свой ExecutionState (ключ — chat.id).

Использование:
    python examples/run_telegram.py <example-dir> <bot-token>

Стоп — Ctrl+C.
"""
from __future__ import annotations

import asyncio
import io
import logging
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_SRC = HERE.parent / "execution-engine" / "src"
sys.path.insert(0, str(ENGINE_SRC))

# Заглушка sandbox_runner — script_execution здесь не используется.
sandbox = types.ModuleType("sandbox_runner")
client_mod = types.ModuleType("sandbox_runner.client")
class _Stub:  # pragma: no cover
    pass
client_mod.PyRunnerClient = _Stub
sys.modules["sandbox_runner"] = sandbox
sys.modules["sandbox_runner.client"] = client_mod

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from models.chatbot import Chatbot
from models.execution_state import ExecutionState, Frame
from models.message import InMessage
from engine.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("tg-bridge")


def _load(example_dir: Path) -> Chatbot:
    bot_path = example_dir / "chatbot.json"
    if not bot_path.exists():
        raise FileNotFoundError(f"{bot_path} не найден")
    return Chatbot.model_validate_json(bot_path.read_text(encoding="utf-8"))


async def main(example_dir: Path, token: str) -> None:
    chatbot = _load(example_dir)
    engines: dict[int, Engine] = {}
    lock = asyncio.Lock()

    async def get_engine(chat_id: int) -> Engine:
        async with lock:
            engine = engines.get(chat_id)
            if engine is None:
                state = ExecutionState(
                    bot_id=chatbot.bot_id,
                    execution_id=chat_id,
                    call_stack=[Frame(executing_node_id=chatbot.graph.root, variable_values={})],
                )
                engine = Engine(chatbot, state)
                engines[chat_id] = engine
                logger.info(f"Создан engine для chat {chat_id}")
            return engine

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    logger.info(f"Подключились как @{me.username} (id={me.id}); пример: {example_dir.name}")

    dp = Dispatcher()

    @dp.message()
    async def handle(message):
        try:
            chat_id = message.chat.id
            engine = await get_engine(chat_id)
            in_msg = InMessage(text=message.text or "", restart_command=False)
            logger.info(f"<- chat {chat_id}: {in_msg.text!r}")
            out = await engine.execute(in_msg)
            reply = out.text or "(пусто)"
            logger.info(f"-> chat {chat_id}: {reply!r}")
            await message.answer(reply)
        except Exception as e:
            logger.exception(f"ошибка обработчика: {e}")
            try:
                await message.answer(f"ошибка: {e}")
            except Exception:
                pass

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


def _entry() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    example_dir = Path(sys.argv[1]).resolve()
    token = sys.argv[2]
    if not example_dir.is_dir():
        print(f"директория {example_dir} не существует", file=sys.stderr)
        return 2
    try:
        asyncio.run(main(example_dir, token))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(_entry())
