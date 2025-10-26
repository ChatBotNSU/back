from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from ..models import BotBlock, RedisMessage, ProcessingResult

class BaseBlockProcessor(ABC):
    """Базовый класс для всех процессоров блоков"""
    
    @abstractmethod
    def get_block_type(self) -> str:
        """Возвращает тип блока, который обрабатывает этот процессор"""
        pass
    
    @abstractmethod
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        """
        Обрабатывает блок сценария
        
        Args:
            block: Блок для обработки
            message: Входящее сообщение
            context: Контекст выполнения (переменные, состояние)
            
        Returns:
            Результат обработки блока
        """
        pass
    
    def get_next_block_id(self, block: BotBlock, context: Dict[str, Any]) -> Optional[str]:
        """Определяет следующий блок на основе условий"""
        if not block.next_blocks:
            return None
            
        for next_block in block.next_blocks:
            condition = next_block.condition
            if self._evaluate_condition(condition, context):
                return next_block.target_block_id
        
        return None
    
    def _evaluate_condition(self, condition: Optional[str], context: Dict[str, Any]) -> bool:
        """Оценивает условие перехода"""
        if condition is None or condition.strip() == "":
            return True
            
        try:
            # Заменяем переменные в условии
            evaluated_condition = self._replace_variables(condition, context)
            
            # Простая оценка булевых выражений
            if evaluated_condition.lower() in ['true', '1', 'yes']:
                return True
            elif evaluated_condition.lower() in ['false', '0', 'no']:
                return False
                
            return bool(evaluated_condition)
        except Exception:
            return False
    
    def _replace_variables(self, text: str, context: Dict[str, Any]) -> str:
        """Заменяет переменные в тексте на значения из контекста"""
        if not isinstance(text, str):
            return text
            
        result = text
        for key, value in context.items():
            if isinstance(value, (str, int, float)):
                placeholder = "{{" + key + "}}"
                result = result.replace(placeholder, str(value))
        return result
    
    def _process_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Обрабатывает значение переменной, заменяя шаблоны"""
        if isinstance(value, str):
            return self._replace_variables(value, context)
        return value