import asyncio

import sys
print(sys.path)


from redis_controller.redis_loop import redis_router
from models import ExecutionRequest, ExecutionResponse
from minio_controller.S3Client import S3Client

from models import OutMessage

from config import get_config

async def execution_requests_processor(request: ExecutionRequest) -> ExecutionResponse:
    print("Processing request:", request)
    return ExecutionResponse(execution_id=1, message=OutMessage(choise_options=["a", "b", "c"]))

async def main():
    config = get_config()
    endpoint = "{}:{}".format(config.s3.host, config.s3.port)
    S3Client(endpoint, config.s3.user, config.s3.password)

    await redis_router(execution_requests_processor)

if __name__ == "__main__":
    asyncio.run(main())
