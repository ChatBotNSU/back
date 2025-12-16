from typing import Annotated

from fastapi import Depends, FastAPI

from poller.preview_poller import router as preview_router
from controller.redis_streams import RedisStreamsController
from sender.preview_sender import PreviewResponseSender

app = FastAPI()
app.include_router(preview_router, prefix="/api/v1/preview", tags=["preview"])