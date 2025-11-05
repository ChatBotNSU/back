from db.crud.user import create_user, list_users
from db.session import async_session_maker

from api.user import router as userRouter
from api.graph import router as graphRouter

from fastapi import FastAPI

app = FastAPI()
app.include_router(userRouter, prefix="/api/v1/user", tags=["user"])
app.include_router(graphRouter, prefix="/api/v1/graph", tags=["graph"])
