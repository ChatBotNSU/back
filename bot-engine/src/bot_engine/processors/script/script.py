import json
from ..base import BaseBlockProcessor
from typing import Any, Dict
from ...models import BotBlock, RedisMessage, ProcessingResult

class ScriptProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Script"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        language = block.config.language or "javascript"
        code = block.config.code or ""
        
        # В реальной реализации здесь будет выполнение кода в соответствующем интерпретаторе
        # Пока эмулируем выполнение JavaScript кода
        try:
            # Простая эмуляция для демонстрации
            if language == "javascript":
                # Заменяем переменные в контексте
                for key, value in context.items():
                    if isinstance(value, (str, int, float)):
                        code = code.replace(f"{{{{{key}}}}}", str(value))
                
                # Эмулируем вычисления (очень упрощенно)
                if "calculateDiscount" in code:
                    # Эмуляция функции calculateDiscount
                    outputs = {
                        "final_price": 90.0,
                        "savings_amount": 10.0
                    }
                else:
                    outputs = {"result": "default_output"}
            else:
                outputs = {"error": f"Unsupported language: {language}"}
            
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
            
        except Exception as e:
            return ProcessingResult(
                response_message=f"Ошибка выполнения скрипта: {str(e)}",
                next_block_id=None,
                outputs={"error": str(e)}
            )