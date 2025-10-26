from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from db.crud.user import create_user, list_users, get_user_by_email
from db.schemas.user import UserCreate, UserRead

router = APIRouter()

@router.post("/", response_model=UserRead)
async def create_user_endpoint(user: UserCreate, session: AsyncSession = Depends(get_session)):
    new_user = await create_user(session, user.name, user.email, user.password_hash)
    return new_user


@router.get("/", response_model=list[UserRead])
async def list_users_endpoint(session: AsyncSession = Depends(get_session)):
    users = await list_users(session)
    return users

@router.get("/get_by_email", response_model=UserRead)
async def get_user_by_email_endpoint(email: str, session: AsyncSession = Depends(get_session)):
    user = await get_user_by_email(session, email)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with email '{email}' not found")
    return user
