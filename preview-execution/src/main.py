from typing import Annotated

from fastapi import Depends, FastAPI

from poller.preview_poller import router as preview_router
from config import get_config

config = get_config()


app = FastAPI()
app.include_router(preview_router, prefix="/api/v1/preview", tags=["preview"])