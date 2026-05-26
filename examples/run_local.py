"""Прогнать пример без Telegram/Redis/MinIO — прямо через Engine.execute.

Использование:
    python examples/run_local.py <example-dir> [message ...]

Если message-ов не передано, скрипт берёт дефолтную последовательность из 5
сообщений. Все ответы и состояние переменных печатаются в stdout.

Пример:
    python examples/run_local.py examples/greeter
    python examples/run_local.py examples/echo "первое" "второе"
"""
from __future__ import annotations

import asyncio
import io
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_SRC = HERE.parent / "execution-engine" / "src"
sys.path.insert(0, str(ENGINE_SRC))

# script_execution мы тут не запускаем — заглушка, чтобы импорт не падал.
sandbox = types.ModuleType("sandbox_runner")
client_mod = types.ModuleType("sandbox_runner.client")
class _Stub:  # pragma: no cover
    pass
client_mod.PyRunnerClient = _Stub
sys.modules["sandbox_runner"] = sandbox
sys.modules["sandbox_runner.client"] = client_mod

# Win-консоль по умолчанию cp1252 — заворачиваем stdout в UTF-8.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from models.chatbot import Chatbot
from models.execution_state import ExecutionState, Frame
from models.message import InMessage
from engine.engine import Engine


DEFAULT_MESSAGES = ["привет", "как дела", "что-то ещё", "четвёртое", "пятое"]


def _load(example_dir: Path) -> Chatbot:
    bot_path = example_dir / "chatbot.json"
    if not bot_path.exists():
        raise FileNotFoundError(f"{bot_path} не найден")
    return Chatbot.model_validate_json(bot_path.read_text(encoding="utf-8"))


async def _run(example_dir: Path, messages: list[str]) -> None:
    chatbot = _load(example_dir)
    state = ExecutionState(
        bot_id=chatbot.bot_id,
        execution_id=1,
        call_stack=[Frame(executing_node_id=chatbot.graph.root, variable_values={})],
    )
    engine = Engine(chatbot, state)
    for i, text in enumerate(messages, start=1):
        out = await engine.execute(InMessage(text=text, restart_command=False))
        vars_ = engine.execution_state.call_stack[0].variable_values
        print(f"[{i}] user > {text}")
        print(f"    bot  < {out.text}")
        print(f"    vars : {vars_}")
        print()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    example_dir = Path(sys.argv[1]).resolve()
    if not example_dir.is_dir():
        print(f"директория {example_dir} не существует", file=sys.stderr)
        return 2
    messages = sys.argv[2:] or DEFAULT_MESSAGES
    asyncio.run(_run(example_dir, messages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
