from ..base import BaseBlockProcessor
from typing import Any, Dict
from ...models import BotBlock, RedisMessage, ProcessingResult

class SubflowProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Subflow"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        flow_id = block.config.flow_id
        inputs = block.config.inputs or {}
        
        # Обрабатываем входные параметры (заменяем переменные)
        processed_inputs = {}
        for key, value in inputs.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                var_name = value[2:-2].strip()
                processed_inputs[key] = context.get(var_name)
            else:
                processed_inputs[key] = value
        
        # В реальной реализации здесь будет вызов подпотока
        # Пока эмулируем успешное выполнение
        outputs = {
            "ticket_number": f"TKT-{hash(flow_id)}",
            "resolution_status": "completed"
        }
        
        # Применяем output bindings
        final_outputs = {}
        for output_key, var_name in block.outputs.items():
            if output_key in outputs:
                final_outputs[var_name] = outputs[output_key]
        
        next_block_id = self.get_next_block_id(block, context)
        
        return ProcessingResult(
            response_message=None,
            next_block_id=next_block_id,
            outputs=final_outputs
        )