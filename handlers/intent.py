from __future__ import annotations

import re
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session

_WORD_RE_CACHE: dict[str, re.Pattern] = {}


def _word_in(keyword: str, text: str) -> bool:
    if keyword not in _WORD_RE_CACHE:
        _WORD_RE_CACHE[keyword] = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
    return bool(_WORD_RE_CACHE[keyword].search(text))


class IntentHandler:
    """
    Simple keyword-based intent matcher.
    In production replace with an NLU model / LLM call.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        input_var = config.get("input_var", "text")
        text: str = str(data_in.get(input_var) or session.variables.get(input_var, ""))

        intents: list[dict[str, Any]] = config.get("intents", [])
        min_confidence: float = float(config.get("confidence", 0.6))
        fallback: str = config.get("fallback", "")

        best_intent = fallback
        best_confidence = 0.0
        entities: dict[str, Any] = {}

        for intent_def in intents:
            name = intent_def.get("name", "")
            keywords: list[str] = intent_def.get("keywords", [])
            if not keywords:
                continue
            hits = sum(1 for kw in keywords if _word_in(kw, text))
            confidence = hits / len(keywords)
            if confidence >= min_confidence and confidence > best_confidence:
                best_confidence = confidence
                best_intent = name
                entities = intent_def.get("entities", {})

        return {
            "intent": best_intent,
            "confidence": best_confidence,
            "entities": entities,
            "matched": best_intent != fallback,
        }


register(NodeType.INTENT, IntentHandler())
