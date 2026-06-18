from __future__ import annotations

import json
import logging
from typing import Any

from engine.validation import validate_flow_graph
from models.flow import Flow
from models.node import Node, NodeType
from services import llm

logger = logging.getLogger(__name__)

# Default model for graph generation — overridable per request / via config.
DEFAULT_MODEL = "gpt-4o-mini"
MAX_ATTEMPTS = 3

_NODE_TYPES = ", ".join(t.value for t in NodeType)

_SYSTEM_PROMPT = f"""\
Ты — генератор графов чат-ботов. По описанию на естественном языке ты строишь \
граф диалога в строгом JSON-формате. Отвечай ТОЛЬКО валидным JSON-объектом, без \
markdown-обёрток и комментариев.

Схема ответа:
{{
  "name": "короткое имя флоу",
  "description": "одно предложение о назначении",
  "start_node": "id стартовой ноды",
  "nodes": [
    {{
      "id": "уникальный строковый id",
      "type": "<один из типов ниже>",
      "label": "человекочитаемая подпись",
      "config": {{}},
      "exec_out": {{
        "conditions": [
          {{"if": "$data.text", "contains": "привет", "goto": "id_следующей_ноды"}}
        ],
        "fallback": "id_ноды_по_умолчанию"
      }}
    }}
  ]
}}

Допустимые type: {_NODE_TYPES}.

Правила:
- start_node ОБЯЗАН ссылаться на существующую ноду, обычно тип message_trigger.
- Каждый goto и fallback ОБЯЗАН ссылаться на существующий id ноды.
- Линейные переходы задавай через exec_out.fallback.
- Условные ветвления — через exec_out.conditions с операторами \
eq/neq/gt/lt/contains/exists/not_exists/in.
- Терминальные ветки заканчивай нодой типа end.
- Не выдумывай типы нод вне списка.

Тексты и сбор данных:
- Любой текст пользователю — ОТДЕЛЬНАЯ нода send_message с непустым config.text. \
Не оставляй config.text пустым.
- Чтобы получить ответ: СНАЧАЛА send_message с вопросом, ЗАТЕМ user_input с \
config.variable (имя переменной), напр. {{"variable": "phone"}}.
- Подставляй ранее собранные ответы в тексты через {{{{переменная}}}} — \
ровно имя из user_input.config.variable. Пример: \
"Заказ: {{{{dish}}}}, адрес {{{{address}}}}, тел {{{{phone}}}}. Верно?".
- НИКОГДА не пиши заглушки вида [текст], [имя], <...> — только {{{{переменная}}}}.
- message_trigger и user_input не показывают текст сами — текст всегда в send_message.
"""


class FlowGenerationError(RuntimeError):
    """Raised when the LLM fails to produce a valid flow after all retries."""

    def __init__(self, message: str, attempts: int, last_errors: list[str]):
        super().__init__(message)
        self.attempts = attempts
        self.last_errors = last_errors


def _strip_fences(raw: str) -> str:
    """Tolerate ```json … ``` wrappers some models still emit."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _build_flow(data: dict[str, Any]) -> Flow:
    nodes: dict[str, Node] = {}
    for nd in data.get("nodes", []):
        node = Node.model_validate(nd)
        nodes[node.id] = node
    return Flow(
        name=data.get("name", "Generated flow"),
        description=data.get("description", ""),
        nodes=nodes,
        start_node=data.get("start_node"),
        metadata={"generated": "llm"},
    )


async def generate_flow(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
    max_attempts: int = MAX_ATTEMPTS,
) -> Flow:
    """
    Generate a runnable Flow from a prompt.

    Uses the LLM when configured; if no LLM is available (or the provider errors),
    falls back to an offline starter scaffold so the product's core loop always
    works. A model that returns invalid JSON after retries surfaces as an error.
    """
    try:
        return await _generate_with_llm(
            prompt, model=model, temperature=temperature, max_attempts=max_attempts
        )
    except llm.LLMUnavailable:
        return generate_offline(prompt)
    except FlowGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — provider/auth/network → graceful scaffold
        logger.warning("LLM generation failed (%s) — using offline scaffold", exc)
        return generate_offline(prompt)


def generate_offline(prompt: str) -> Flow:
    """Deterministic starter flow derived from the prompt (no LLM required)."""
    name = prompt.strip().split("\n")[0][:48] or "Новый флоу"
    nodes = [
        Node(id="greet", type=NodeType.SEND_MESSAGE, label="Приветствие",
             config={"text": "Здравствуйте! 👋 Чем могу помочь?"},
             exec_out={"conditions": [], "fallback": "ask"}),  # type: ignore[arg-type]
        Node(id="ask", type=NodeType.USER_INPUT, label="Вопрос",
             config={"variable": "answer"},
             exec_out={"conditions": [], "fallback": "reply"}),  # type: ignore[arg-type]
        Node(id="reply", type=NodeType.SEND_MESSAGE, label="Ответ",
             config={"text": "Спасибо! Передал ваш запрос — скоро вернёмся."},
             exec_out={"conditions": [], "fallback": "end"}),  # type: ignore[arg-type]
        Node(id="end", type=NodeType.END, label="Конец"),
    ]
    return Flow(
        name=name,
        description=prompt,
        nodes={n.id: n for n in nodes},
        start_node="greet",
        metadata={"generated": "offline", "prompt": prompt},
    )


async def _generate_with_llm(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
    max_attempts: int = MAX_ATTEMPTS,
) -> Flow:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    last_errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        raw = await llm.acomplete(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(_strip_fences(raw))
            flow = _build_flow(data)
            errors = validate_flow_graph(flow)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            errors = [f"Не удалось разобрать ответ модели: {exc}"]
            flow = None  # type: ignore[assignment]

        if flow is not None and not errors:
            return flow

        last_errors = errors
        if attempt < max_attempts:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "В предыдущем ответе ошибки:\n- "
                        + "\n- ".join(errors)
                        + "\nИсправь и пришли ПОЛНЫЙ валидный JSON заново."
                    ),
                }
            )

    raise FlowGenerationError(
        f"Не удалось сгенерировать валидный флоу за {max_attempts} попыток",
        attempts=max_attempts,
        last_errors=last_errors,
    )


async def improve_flow(
    flow: Flow,
    chat_history: list[dict[str, Any]] | None = None,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
) -> dict[str, Any]:
    """
    Analyse an existing flow (optionally with sample chat history) and return
    a structured list of improvement suggestions. Does not mutate the flow.
    """
    flow_json = {
        "name": flow.name,
        "description": flow.description,
        "start_node": flow.start_node,
        "nodes": [n.model_dump(by_alias=True, mode="json") for n in flow.nodes.values()],
    }

    system = (
        "Ты — аналитик диалоговых сценариев. Тебе дают граф чат-бота и (опционально) "
        "историю реальных диалогов. Найди слабые места: тупики, недостающие ветки, "
        "неясные сообщения, места отвала пользователей. Ответь ТОЛЬКО JSON-объектом "
        'вида {"suggestions": [{"node_id": "...|null", "issue": "...", '
        '"recommendation": "..."}], "summary": "..."}.'
    )
    user_parts = [f"Граф флоу:\n{json.dumps(flow_json, ensure_ascii=False)}"]
    if chat_history:
        user_parts.append(
            f"История диалогов:\n{json.dumps(chat_history, ensure_ascii=False)}"
        )

    raw = await llm.acomplete(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )

    try:
        return json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        return {"suggestions": [], "summary": raw}
