import asyncio
import logging


from redis_controller.redis_loop import redis_router
from models import ExecutionRequest, ExecutionResponse
from minio_controller.S3Client import S3Client

from models import OutMessage
from engine.engine_factory import EngineFactory
from config import get_config

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)




async def execution_requests_processor(request: ExecutionRequest) -> ExecutionResponse:
    logger.info("Started executing request")
    engineFactory = EngineFactory()
    engine = engineFactory.get_engine(request.execution_id, request.chatbot_id)
    message = await engine.execute(request.message)
    return ExecutionResponse(execution_id=request.execution_id, message=message)

async def main():
    config = get_config()
    endpoint = "{}:{}".format(config.s3.host, config.s3.port)
    S3Client(endpoint, config.s3.user, config.s3.password)  


    await redis_router(execution_requests_processor)

if __name__ == "__main__":
    asyncio.run(main())
