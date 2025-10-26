from ..base import BaseBlockProcessor
from ...models import BotBlock, RedisMessage, ProcessingResult
from typing import Any, Dict

class ConditionProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Condition"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        expression = block.config.expression or ""
        
        # Оцениваем условие
        condition_result = self._evaluate_complex_condition(expression, context)
        
        # Определяем следующий блок на основе результата условия
        next_block_id = None
        for next_block in block.next_blocks:
            handle = next_block.source_handle
            if (handle == "true" and condition_result) or (handle == "false" and not condition_result):
                next_block_id = next_block.target_block_id
                break
        
        return ProcessingResult(
            response_message=None,
            next_block_id=next_block_id,
            outputs={},
            condition_evaluated=condition_result
        )
    
    def _evaluate_complex_condition(self, expression: str, context: Dict[str, Any]) -> bool:
        """Оценивает сложные логические выражения"""
        try:
            # Заменяем переменные в выражении
            evaluated_expr = self._replace_variables(expression, context)
            
            # Упрощенная оценка (в реальной реализации нужен безопасный eval)
            if "==" in evaluated_expr:
                left, right = evaluated_expr.split("==", 1)
                return left.strip() == right.strip().strip('"\'')
            elif "!=" in evaluated_expr:
                left, right = evaluated_expr.split("!=", 1)
                return left.strip() != right.strip().strip('"\'')
            elif ">" in evaluated_expr:
                left, right = evaluated_expr.split(">", 1)
                return float(left.strip()) > float(right.strip())
            elif "<" in evaluated_expr:
                left, right = evaluated_expr.split("<", 1)
                return float(left.strip()) < float(right.strip())
            
            return bool(evaluated_expr)
        except Exception:
            return False