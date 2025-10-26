from ..base import BaseBlockProcessor
from typing import Any, Dict
from ...models import BotBlock, RedisMessage, ProcessingResult

class StartProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Start"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        # Start блок просто передает управление следующему блоку
        # Может использоваться для инициализации переменных
        
        # Обрабатываем входные параметры если они есть
        outputs = {}
        if block.config.inputs:
            for input_key, input_value in block.config.inputs.items():
                # В реальной реализации здесь будет обработка входных параметров потока
                outputs[input_key] = input_value
        
        next_block_id = self.get_next_block_id(block, context)
        
        return ProcessingResult(
            response_message=None,
            next_block_id=next_block_id,
            outputs=outputs
        )