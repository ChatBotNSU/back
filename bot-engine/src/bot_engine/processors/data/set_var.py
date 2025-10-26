from ..base import BaseBlockProcessor
from ...models import BotBlock, RedisMessage, ProcessingResult
from typing import Any, Dict

class SetVarProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "SetVar"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        variables = block.config.variables or {}
        
        # Обрабатываем значения переменных (может содержать выражения)
        processed_vars = {}
        for key, value in variables.items():
            processed_vars[key] = self._process_value(value, context)
        
        return ProcessingResult(
            response_message=None,
            next_block_id=self.get_next_block_id(block, context),
            outputs=processed_vars
        )
    
    def _process_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Обрабатывает значение переменной, заменяя шаблоны"""
        if isinstance(value, str):
            return self._replace_variables(value, context)
        return value