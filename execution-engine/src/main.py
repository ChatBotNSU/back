import asyncio

import sys
print(sys.path)


from redis_controller.redis_loop import redis_router
from models import ExecutionRequest, ExecutionResponse

from models import OutMessage

async def execution_requests_processor(request: ExecutionRequest) -> ExecutionResponse:
    print("Processing request:", request)
    return ExecutionResponse(execution_id=1, message=OutMessage(choise_options=["a", "b", "c"]))

async def main():
    await redis_router(execution_requests_processor)

if __name__ == "__main__":
    asyncio.run(main())
