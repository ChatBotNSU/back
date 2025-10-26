from ..base import BaseBlockProcessor
from ...models import BotBlock, RedisMessage, ProcessingResult
from typing import Any, Dict

class AnswerProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Answer"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        question = block.config.question or ""
        variable_name = block.config.variable or "user_input"
        
        # Если это первый вызов - задаем вопрос
        waiting_key = f"_waiting_for_{variable_name}"
        if not context.get(waiting_key):
            return ProcessingResult(
                response_message=question,
                next_block_id=None,  # Ожидаем ответ пользователя
                outputs={},
                waiting_for_input=True,
                expected_variable=variable_name
            )
        else:
            # Обрабатываем ответ пользователя
            user_input = message.message
            validation_result = self._validate_input(user_input, block.config.validation)
            
            outputs = {
                variable_name: user_input,
                f"{variable_name}_valid": validation_result
            }
            
            # Определяем следующий блок на основе валидации
            next_block_id = None
            if validation_result:
                for next_block in block.next_blocks:
                    if next_block.source_handle == "success":
                        next_block_id = next_block.target_block_id
                        break
            else:
                for next_block in block.next_blocks:
                    if next_block.source_handle == "error":
                        next_block_id = next_block.target_block_id
                        break
            
            return ProcessingResult(
                response_message=None,
                next_block_id=next_block_id,
                outputs=outputs
            )
    
    def _validate_input(self, input_value: str, validation_config: Dict[str, Any]) -> bool:
        """Валидирует ввод пользователя"""
        if not validation_config:
            return True
            
        validation_type = validation_config.get("type", "text")
        
        if validation_type == "email":
            import re
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return bool(re.match(pattern, input_value))
        elif validation_type == "number":
            try:
                float(input_value)
                return True
            except ValueError:
                return False
        elif validation_type == "text":
            min_length = validation_config.get("minLength", 1)
            return len(input_value) >= min_length
            
        return True