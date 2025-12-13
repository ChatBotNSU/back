import logging

from .engine import Engine
from minio_controller.S3Client import S3Client


logger = logging.getLogger("app")

class EngineFactory:
    '''Singleton class that provides access to created engines and creates new ones when needed'''

    _instance = None
    existing_engines: dict[int, Engine] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EngineFactory, cls).__new__(cls)
        return cls._instance

    def get_engine(self, execution_id: int, chatbot_id: int) -> Engine:
        if execution_id in self.existing_engines:
            return self.existing_engines[execution_id]

        s3client = S3Client.get_instance()

        chatbot = s3client.download_chatbot(chatbot_id)
        execution = s3client.download_execution(execution_id)

        engine = Engine(chatbot, execution)
        self.existing_engines[execution_id] = engine
        logger.info("Engine instatiated")
        return engine
