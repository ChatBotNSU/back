import asyncio

from redis_controller.redis_loop import redis_router
from models import ExecutionRequest, ExecutionResponse
from minio_controller.S3Client import S3Client

from models import OutMessage
from engine.engine_factory import EngineFactory
from config import get_config

# dry_run should be switched to that when EngineFactory and Engine will be completed
async def execution_requests_processor(request: ExecutionRequest) -> ExecutionResponse:
    engineFactory = EngineFactory()
    engine = engineFactory.get_engine(request.execution_id, request.chatbot_id)
    message = await engine.execute(request.message)
    return ExecutionResponse(execution_id=request.execution_id, message=message)

# Only for example that the code is working
async def execution_requests_processor_dry_run(request: ExecutionRequest) -> ExecutionResponse:
    print("Processing request:", request)
    return ExecutionResponse(execution_id=1, message=OutMessage(choise_options=["a", "b", "c"]))

async def main():
    config = get_config()
    endpoint = "{}:{}".format(config.s3.host, config.s3.port)
    S3Client(endpoint, config.s3.user, config.s3.password)  

    await redis_router(execution_requests_processor_dry_run)

if __name__ == "__main__":
    asyncio.run(main())
