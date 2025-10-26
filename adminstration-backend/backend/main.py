from typing import Annotated

from fastapi import Depends, FastAPI
from api.middleware import get_current_active_user
from entities.User import User

from api.auth import router as auth_router

# to get a string like this run:
# openssl rand -hex 32



app = FastAPI()
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])

@app.get("/users/me/", response_model=User)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return current_user


@app.get("/users/me/items/")
async def read_own_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return [{"item_id": "Foo", "owner": current_user.name}]
