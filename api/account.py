from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api.auth import IdentityDep
from api.deps import UserStoreDep
from services.security import create_token, hash_password, verify_password
from stores.user_store import User, new_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str = ""

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    workspace_id: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


def _public(user: User) -> UserPublic:
    return UserPublic(id=user.id, email=user.email, name=user.name, workspace_id=user.workspace_id)


def _issue(user: User) -> AuthResponse:
    token = create_token({"sub": user.id, "ws": user.workspace_id})
    return AuthResponse(token=token, user=_public(user))


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, users: UserStoreDep) -> AuthResponse:
    if await users.get_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = new_user(str(body.email), hash_password(body.password), body.name)
    await users.create(user)
    return _issue(user)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, users: UserStoreDep) -> AuthResponse:
    user = await users.get_by_email(str(body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue(user)


@router.get("/me", response_model=UserPublic)
async def me(identity: IdentityDep, users: UserStoreDep) -> UserPublic:
    if not identity.user_id:
        raise HTTPException(status_code=401, detail="Not a user session")
    user = await users.get_by_id(identity.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _public(user)
