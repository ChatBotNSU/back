from typing import Annotated

from fastapi import Depends, FastAPI

from api.telegram_api import router as telegram_router

app = FastAPI()
app.include_router(telegram_router, prefix="/api/v1/telegram", tags=["telegram"])