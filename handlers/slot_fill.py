from __future__ import annotations

import json
import logging
import re
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session
from services import llm

logger = logging.getLogger(__name__)


async def _llm_extract_slot(
    model: str, slot_def: dict[str, Any], raw_reply: str
) -> Any:
    """Ask the LLM to extract the named field from the user's reply.

    Returns the extracted value, or None when the reply doesn't clearly
    contain it. Falls back to None on any LLM error — caller stores the raw
    text instead.
    """
    name = slot_def["name"]
    desc = slot_def.get("description") or slot_def.get("question") or name
    sys_msg = (
        "Ты — модуль извлечения одного поля из реплики пользователя. "
        "Верни СТРОГО один JSON-объект с одним ключом без markdown и комментариев.\n"
        f"Поле: {name} — {desc}.\n"
        "Если в реплике значения нет — верни {\"" + name + "\": null}. "
        "Не выдумывай. Не оборачивай в строки и не нормализуй: возвращай как сказал пользователь."
    )
    raw = await llm.acomplete(
        model,
        [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": raw_reply},
        ],
        temperature=0.0,
    )
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        s = s[i : j + 1]
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    val = data.get(name)
    if val in (None, "", []):
        return None
    return val


def _lookup(key: str, variables: dict[str, Any]) -> Any:
    cur: Any = variables
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _render(template: str, variables: dict[str, Any]) -> str:
    def replacer(match: re.Match) -> str:
        key = match.group(1).strip()
        val = _lookup(key, variables)
        return str(val) if val is not None else match.group(0)
    return re.sub(r"\{\{(.+?)\}\}", replacer, template)


class SlotFillHandler:
    """
    Collects multiple slots from the user one by one.
    Each call checks which slots are still missing and asks for the next one.
    Uses __pending_input__ for the resume-flow protocol.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        slots_config: list[dict[str, Any]] = config.get("slots", [])
        max_attempts: int = config.get("max_attempts", 3)
        use_llm: bool = bool(config.get("use_llm", True))
        model: str = config.get("model", "yandexgpt-lite")

        # Load or initialise slot state stored in session
        slot_state_key = f"__slot_state_{node.id}__"
        slot_state: dict[str, Any] = session.variables.get(slot_state_key, {})

        # Process a pending answer if available
        pending = session.variables.pop("__pending_input__", None)
        waiting_slot = slot_state.get("__waiting_slot__")
        if pending is not None and waiting_slot:
            slot_def = next((s for s in slots_config if s.get("name") == waiting_slot), None)
            value: Any = str(pending)
            if use_llm and slot_def:
                # Ask the LLM to pull the field's value out of the natural-language
                # reply — so "Меня зовут Митрофан" → "Митрофан", not the whole
                # phrase. On failure (LLM down, didn't parse, returned null) we
                # keep the raw text, which is at worst no worse than the old
                # behaviour.
                try:
                    extracted = await _llm_extract_slot(model, slot_def, str(pending))
                    if extracted is not None:
                        value = extracted
                except llm.LLMUnavailable:
                    pass
                except Exception:  # noqa: BLE001
                    logger.warning("slot_fill: LLM extraction failed", exc_info=True)
            slot_state[waiting_slot] = value
            # Expose the collected slot as a top-level variable so {{slot_name}}
            # in subsequent prompts (or downstream nodes) resolves naturally.
            session.variables[waiting_slot] = value
            slot_state.pop("__waiting_slot__", None)
            attempts = slot_state.get("__attempts__", {})
            attempts[waiting_slot] = 0
            slot_state["__attempts__"] = attempts

        session.variables[slot_state_key] = slot_state

        # Find the next missing slot
        for slot_def in slots_config:
            name = slot_def["name"]
            if name not in slot_state or slot_state[name] is None:
                attempts: dict[str, int] = slot_state.get("__attempts__", {})
                if attempts.get(name, 0) >= max_attempts:
                    # Too many retries — mark as failed
                    slot_state["__failed__"] = True
                    session.variables[slot_state_key] = slot_state
                    return self._build_output(slot_state, slots_config, complete=False)

                attempts[name] = attempts.get(name, 0) + 1
                slot_state["__attempts__"] = attempts
                slot_state["__waiting_slot__"] = name
                session.variables[slot_state_key] = slot_state

                question = _render(
                    slot_def.get("question", f"Please provide {name}"),
                    session.variables,
                )
                session.variables["__slot_question__"] = question
                session.variables["__waiting_node__"] = node.id

                await self._send_question(session, question)
                return {"__waiting__": True}

        # All slots collected — clear the stale slot_question so a downstream
        # WAITING node doesn't surface this handler's last prompt as if it
        # were its own (DemoChat reads __slot_question__ from session vars).
        session.variables.pop("__slot_question__", None)
        return self._build_output(slot_state, slots_config, complete=True)

    @staticmethod
    async def _send_question(session: Session, question: str) -> None:
        """Deliver the slot question via the channel adapter. Best-effort: a
        failure (no adapter, no token, network) does not break the flow — the
        slot state is already persisted and will replay on next inbound message.
        """
        message: dict[str, Any] = {"content_type": "text", "text": question}
        session.variables.setdefault("__messages__", []).append(message)

        channel = session.variables.get("channel", "")
        recipient = str(
            session.variables.get("chat_id")
            or session.variables.get("user_id")
            or ""
        )
        bot_token = session.variables.get("__bot_token__", "")
        if not (channel and recipient and bot_token):
            return  # playground / test context — nothing to deliver to

        try:
            from adapters import registry as adapter_registry
            await adapter_registry.send(channel, bot_token, recipient, message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("slot_fill: failed to deliver question: %s", exc)

    @staticmethod
    def _build_output(
        slot_state: dict[str, Any],
        slots_config: list[dict[str, Any]],
        complete: bool,
    ) -> dict[str, Any]:
        slots = {s["name"]: slot_state.get(s["name"]) for s in slots_config}
        return {
            "slots": slots,
            "complete": complete,
            "attempts": slot_state.get("__attempts__", {}),
            "__waiting__": False,
        }


register(NodeType.SLOT_FILL, SlotFillHandler())
