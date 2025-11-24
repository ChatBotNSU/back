from api.user import router as userRouter
from api.chatbot import router as chatbotRouter
from api.execution import router as executionRouter

from fastapi import FastAPI

app = FastAPI()
app.include_router(userRouter, prefix="/api/v1/user", tags=["user"])
app.include_router(chatbotRouter, prefix="/api/v1/chatbot", tags=["chatbot"])
app.include_router(executionRouter, prefix="/api/v1/execution", tags=["execution"])