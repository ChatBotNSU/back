from ..base import BaseBlockProcessor
from typing import Any, Dict
from ...models import BotBlock, RedisMessage, ProcessingResult

class SwitchProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Switch"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        variable_name = block.config.variable or ""
        
        # Извлекаем значение переменной из контекста
        variable_value = None
        if variable_name.startswith("{{") and variable_name.endswith("}}"):
            var_key = variable_name[2:-2].strip()
            variable_value = context.get(var_key)
        else:
            variable_value = context.get(variable_name)
        
        # Ищем подходящий case
        matched_case = None
        for case in block.config.cases or []:
            case_value = case.get("value")
            if str(case_value) == str(variable_value):
                matched_case = case
                break
        
        # Если не нашли подходящий case, используем default
        if not matched_case:
            matched_case = block.config.default_case or {}
        
        next_block_id = matched_case.get("targetBlockId")
        
        return ProcessingResult(
            response_message=None,
            next_block_id=next_block_id,
            outputs={
                "switch_variable": variable_name,
                "switch_value": variable_value,
                "matched_case": matched_case.get("value") if matched_case else "default"
            }
        )