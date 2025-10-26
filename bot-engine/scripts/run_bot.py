import os
import logging
from dotenv import load_dotenv
from bot_engine.engine import BotEngine

# Загружаем переменные окружения
load_dotenv()

def main():
    # Настройка логирования
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Создаем и запускаем движок
    engine = BotEngine(
        redis_host=os.getenv('REDIS_HOST', 'localhost'),
        redis_port=int(os.getenv('REDIS_PORT', 6379)),
        redis_stream=os.getenv('REDIS_STREAM', 'bot-messages'),
        consumer_group=os.getenv('REDIS_CONSUMER_GROUP', 'bot-engine'),
        minio_endpoint=os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
        minio_access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
        minio_secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
        minio_bucket=os.getenv('MINIO_BUCKET', 'bot-scenarios'),
        secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true'
    )
    
    try:
        engine.listen_for_messages()
    except KeyboardInterrupt:
        print("\nBot engine stopped")

if __name__ == "__main__":
    main()