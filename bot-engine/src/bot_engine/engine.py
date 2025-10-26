import json
import logging
from typing import Dict, Any, Optional
import redis
from minio import Minio
from minio.error import S3Error

from .models import RedisMessage, BotScenario, BotBlock
from .processors import ProcessorFactory

class BotEngine:
    def __init__(
        self, 
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        redis_stream: str = 'bot-messages',
        consumer_group: str = 'bot-engine',
        minio_endpoint: str = 'localhost:9000',
        minio_access_key: str = 'minioadmin',
        minio_secret_key: str = 'minioadmin',
        minio_bucket: str = 'bot-scenarios',
        secure: bool = False
    ):
        # Инициализация клиентов
        self.redis_client = redis.Redis(
            host=redis_host, port=redis_port, decode_responses=True
        )
        
        self.minio_client = Minio(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=secure
        )
        
        self.redis_stream = redis_stream
        self.consumer_group = consumer_group
        self.minio_bucket = minio_bucket
        self.consumer_name = f"consumer-{redis_host}-{redis_port}"
        
        # Кэш сценариев и состояний пользователей
        self.scenario_cache: Dict[str, BotScenario] = {}
        self.user_sessions: Dict[str, Dict[str, Any]] = {}
        
        self._setup_infrastructure()
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _setup_infrastructure(self):
        """Настройка Redis и MinIO"""
        try:
            self.redis_client.xgroup_create(
                name=self.redis_stream,
                groupname=self.consumer_group,
                id='0',
                mkstream=True
            )
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise e
        
        try:
            if not self.minio_client.bucket_exists(self.minio_bucket):
                self.minio_client.make_bucket(self.minio_bucket)
        except S3Error as e:
            self.logger.error(f"MinIO error: {e}")
            raise

    def get_bot_scenario(self, bot_id: str) -> Optional[BotScenario]:
        """Загружает сценарий из MinIO"""
        try:
            if bot_id in self.scenario_cache:
                return self.scenario_cache[bot_id]
            
            object_name = f"{bot_id}.json"
            response = self.minio_client.get_object(self.minio_bucket, object_name)
            scenario_data = json.loads(response.data.decode('utf-8'))
            response.close()
            response.release_conn()
            
            scenario = BotScenario(**scenario_data)
            self.scenario_cache[bot_id] = scenario
            return scenario
            
        except S3Error as e:
            self.logger.error(f"Scenario {bot_id} not found: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error loading scenario {bot_id}: {e}")
            return None

    def get_user_session(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """Получает или создает сессию пользователя"""
        session_key = f"{user_id}:{session_id}"
        if session_key not in self.user_sessions:
            self.user_sessions[session_key] = {
                "variables": {},
                "current_block": None,
                "waiting_for_input": False,
                "expected_variable": None
            }
        return self.user_sessions[session_key]

    def process_message(self, message: RedisMessage) -> Dict[str, Any]:
        """Обрабатывает сообщение через соответствующий процессор"""
        self.logger.info(f"Processing message for bot {message.bot_id}, block {message.block_id}")
    
        # Загрузка сценария
        scenario = self.get_bot_scenario(message.bot_id)
        if not scenario:
            return {"error": f"Scenario for bot {message.bot_id} not found"}
    
        # Получение сессии пользователя
        session = self.get_user_session(message.user_id or "unknown", message.session_id or "default")
    
        # Определение текущего блока
        current_block_id = message.block_id or session.get("current_block") or scenario.start_block_id
        current_block = scenario.blocks.get(current_block_id)
        if not current_block:
            return {"error": f"Block {current_block_id} not found"}
    
        # Получение процессора для типа блока
        processor = ProcessorFactory.get_processor(current_block.type)
        if not processor:
            return {"error": f"No processor for block type {current_block.type}"}
    
        # Создание контекста выполнения
        context = {
            **session["variables"],
            "user_id": message.user_id,
            "session_id": message.session_id,
            "user_message": message.message
        }
    
        # Обработка блока
        try:
            result = processor.process(current_block, message, context)
        
            # Обновление сессии - обращаемся к атрибутам модели, а не используем .get()
            session["variables"].update(result.outputs)
            session["current_block"] = result.next_block_id
            session["waiting_for_input"] = result.waiting_for_input
            session["expected_variable"] = result.expected_variable
        
            # Формирование ответа
            response = {
                    "bot_id": message.bot_id,
                    "user_id": message.user_id,
                "session_id": message.session_id,
                "response": result.response_message,
                "next_block_id": result.next_block_id,
                "outputs": result.outputs
            }
        
            # Добавляем дополнительные поля если они есть
            if result.quick_replies:
                response["quick_replies"] = result.quick_replies
            if result.choices:
                response["choices"] = result.choices
        
            return response
        
        except Exception as e:
            self.logger.error(f"Error processing block {current_block_id}: {e}")
            return {"error": f"Processing error: {str(e)}"}

    def listen_for_messages(self):
        """Основной цикл обработки сообщений"""
        self.logger.info("Starting bot engine...")
        
        while True:
            try:
                messages = self.redis_client.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.redis_stream: '>'},
                    count=10,
                    block=5000
                )
                
                if not messages:
                    continue
                
                for stream, message_list in messages:
                    for message_id, message_data in message_list:
                        try:
                            # Парсинг сообщения
                            redis_message = RedisMessage(
                                message=message_data.get('message', ''),
                                bot_id=message_data.get('botId', ''),
                                block_id=message_data.get('blockId', ''),
                                user_id=message_data.get('userId'),
                                session_id=message_data.get('sessionId')
                            )
                            
                            # Обработка
                            response = self.process_message(redis_message)
                            
                            # Отправка ответа (можно в другую Redis stream)
                            self._send_response(response)
                            
                            # Подтверждение обработки
                            self.redis_client.xack(
                                self.redis_stream,
                                self.consumer_group,
                                message_id
                            )
                            
                            self.logger.info(f"Processed message {message_id}")
                            
                        except Exception as e:
                            self.logger.error(f"Error processing message {message_id}: {e}")
                            
            except Exception as e:
                self.logger.error(f"Error in message loop: {e}")
                import time
                time.sleep(5)

    def _send_response(self, response: Dict[str, Any]):
        """Отправляет ответ пользователю"""
        if response.get("response"):
            self.logger.info(f"🤖 Bot response: {response['response']}")
    
        if response.get("error"):
            self.logger.error(f"❌ Error: {response['error']}")
    
        # Преобразуем ответ в JSON строку для Redis
        try:
            import json
            response_json = json.dumps(response, ensure_ascii=False)
        
            self.redis_client.xadd(
                'bot-responses',
                {'response': response_json},
                maxlen=1000  # Ограничиваем длину stream
            )
            self.logger.info("✅ Response sent to Redis stream 'bot-responses'")
        
        except Exception as e:
            self.logger.error(f"Failed to send response to Redis: {e}")

def main():
    engine = BotEngine()
    engine.listen_for_messages()

if __name__ == "__main__":
    main()