from __future__ import annotations

import json
import re
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session
from services import llm


def _render(template: str, variables: dict[str, Any]) -> str:
    def replacer(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))
    return re.sub(r"\{\{(.+?)\}\}", replacer, template)


class AiHandler:
    """
    Calls an LLM via LiteLLM.
    Falls back to a stub when litellm is not installed (useful in tests).
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        mode = config.get("mode", "generate")
        model = config.get("model", "gpt-4o-mini")
        temperature = float(config.get("temperature", 0.7))
        output_schema = config.get("output_schema")

        vars_ctx = {**session.variables, **data_in}
        prompt = _render(config.get("prompt", ""), vars_ctx)

        messages = list(config.get("context_msgs", []))
        messages.append({"role": "user", "content": prompt})

        if output_schema:
            messages[-1]["content"] += (
                f"\n\nRespond ONLY with valid JSON matching this schema:\n{json.dumps(output_schema)}"
            )

        # Route through the shared LLM service so the AI node honours the
        # configured provider (YandexGPT / litellm). Falls back to a stub when
        # no backend is available (e.g. in tests).
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        try:
            raw = await llm.acomplete(model, messages, temperature=temperature)
        except llm.LLMUnavailable:
            raw = config.get("__test_response__", "stub response")

        result: Any = raw
        if output_schema:
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = raw

        output_var = config.get("output_var")
        if output_var:
            session.variables[output_var] = result

        return {"result": result, "usage": usage, "model": model}


register(NodeType.AI, AiHandler())
