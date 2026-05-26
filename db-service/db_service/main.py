from db.crud.user import create_user, list_users
from db.session import async_session_maker

from api.user import router as userRouter
from api.chatbot import router as chatbotRouter
from api.subgraph import router as subgraphRouter

from fastapi import FastAPI

app = FastAPI()
app.include_router(userRouter, prefix="/api/v1/user", tags=["user"])
app.include_router(chatbotRouter, prefix="/api/v1/chatbot", tags=["chatbot"])
app.include_router(subgraphRouter, prefix="/api/v1/subgraph", tags=["subgraph"])
