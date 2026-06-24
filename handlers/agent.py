from __future__ import annotations

import json
import re
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session
from services import llm

_AFFIRM = {"да", "yes", "y", "ага", "ок", "окей", "верно", "+", "подтверждаю", "confirm"}


def _extract_json(raw: str) -> dict[str, Any]:
    """Best-effort parse of an LLM reply into a JSON object (handles ``` fences)."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        s = s[i : j + 1]
    try:
        data = json.loads(s)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


async def _llm_extract(
    model: str, fields: list[dict[str, Any]], collected: dict[str, Any], message: str
) -> dict[str, Any]:
    field_lines = "\n".join(
        f"- {f['name']}: {f.get('description') or f.get('question') or f['name']}" for f in fields
    )
    sys = (
        "Ты — модуль извлечения параметров из реплики пользователя. "
        "Верни СТРОГО один JSON-объект без пояснений и без markdown.\n"
        f"Поля для извлечения:\n{field_lines}\n"
        "Включай в JSON только те поля, значения которых явно есть в сообщении. "
        "Ничего не выдумывай. Значения — в естественном виде."
    )
    usr = (
        f"Уже известно: {json.dumps(collected, ensure_ascii=False)}\n"
        f"Сообщение пользователя: {message}"
    )
    raw = await llm.acomplete(
        model,
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        temperature=0.0,
    )
    return _extract_json(raw)


async def _deliver(session: Session, text: str) -> None:
    """Send a question to the user: queue it as a message, surface it for the
    preview UI, and push it through the channel adapter when running live."""
    msg = {"content_type": "text", "text": text}
    session.variables.setdefault("__messages__", []).append(msg)
    session.variables["__slot_question__"] = text

    channel = session.variables.get("channel", "")
    recipient = str(session.variables.get("chat_id") or session.variables.get("user_id") or "")
    bot_token = session.variables.get("__bot_token__", "")
    if channel and recipient and bot_token:
        try:
            from adapters import registry as adapter_registry
            await adapter_registry.send(channel, bot_token, recipient, msg)
        except Exception:  # noqa: BLE001 — delivery is best-effort
            pass


class AgentHandler:
    """
    LLM-driven slot collection with two modes:

    * **agent**    — the LLM extracts several fields from a single message at
      once, asks one combined clarifying question for whatever is still missing,
      then a confirmation step.
    * **fail-safe** — strict one-question-at-a-time collection (also the
      automatic degradation path when the LLM is unavailable or errors out).

    Built on the same wait/resume protocol as ``slot_fill``.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        fields: list[dict[str, Any]] = config.get("fields", [])
        mode: str = config.get("mode", "agent")
        model: str = config.get("model", "yandexgpt-lite")
        confirm: bool = config.get("confirm", True)
        max_attempts: int = int(config.get("max_attempts", 3))
        output_var: str = config.get("output_var", "agent")

        state_key = f"__agent_{node.id}__"
        state: dict[str, Any] = session.variables.get(
            state_key, {"collected": {}, "stage": "collect", "attempts": {}, "failsafe": False}
        )
        collected: dict[str, Any] = state["collected"]

        pending = session.variables.pop("__pending_input__", None)
        incoming = pending if pending is not None else session.variables.get("text", "")

        # ── confirmation stage ───────────────────────────────────────────────
        if state.get("stage") == "confirm":
            if str(incoming).strip().lower() in _AFFIRM:
                return self._complete(session, state_key, collected, fields, output_var)
            collected.clear()
            state["stage"] = "collect"
            session.variables[state_key] = state
            await _deliver(session, "Хорошо, давайте уточним заново.")
            session.variables["__waiting_node__"] = node.id
            return {"__waiting__": True}

        # ── collect stage ────────────────────────────────────────────────────
        agent_mode = mode == "agent" and not state.get("failsafe")

        if agent_mode and incoming:
            try:
                extracted = await _llm_extract(model, fields, collected, str(incoming))
                for f in fields:
                    name = f["name"]
                    val = extracted.get(name)
                    if name not in collected and val not in (None, "", []):
                        collected[name] = val
            except llm.LLMUnavailable:
                state["failsafe"] = True
            except Exception:  # noqa: BLE001 — any extraction failure → degrade
                state["failsafe"] = True
        elif incoming:
            waiting = state.get("waiting_field")
            if waiting:
                collected[waiting] = incoming

        state["collected"] = collected
        missing = [f for f in fields if f["name"] not in collected or collected[f["name"]] in (None, "")]

        if missing:
            if state.get("failsafe") or not agent_mode:
                target = missing[0]
                name = target["name"]
                attempts: dict[str, int] = state.setdefault("attempts", {})
                attempts[name] = attempts.get(name, 0) + 1
                if attempts[name] > max_attempts:
                    return self._complete(session, state_key, collected, fields, output_var, complete=False)
                state["waiting_field"] = name
                question = target.get("question", f"Укажите: {name}")
            else:
                labels = ", ".join(m.get("question", m["name"]) for m in missing)
                state["waiting_field"] = missing[0]["name"]
                question = f"Уточните, пожалуйста: {labels}"
            session.variables[state_key] = state
            await _deliver(session, question)
            session.variables["__waiting_node__"] = node.id
            return {"__waiting__": True}

        # ── all collected → confirm once ─────────────────────────────────────
        if confirm:
            state["stage"] = "confirm"
            session.variables[state_key] = state
            summary = "; ".join(
                f"{f.get('question', f['name'])} — {collected.get(f['name'])}" for f in fields
            )
            await _deliver(session, f"Проверьте, всё верно?\n{summary}\n(да / нет)")
            session.variables["__waiting_node__"] = node.id
            return {"__waiting__": True}

        return self._complete(session, state_key, collected, fields, output_var)

    @staticmethod
    def _complete(
        session: Session,
        state_key: str,
        collected: dict[str, Any],
        fields: list[dict[str, Any]],
        output_var: str,
        complete: bool = True,
    ) -> dict[str, Any]:
        # Expose each collected field as a top-level variable for downstream {{x}}.
        for f in fields:
            session.variables[f["name"]] = collected.get(f["name"])
        session.variables.pop(state_key, None)
        session.variables.pop("__slot_question__", None)
        return {output_var: dict(collected), "fields": dict(collected), "complete": complete, "__waiting__": False}


register(NodeType.AGENT, AgentHandler())
