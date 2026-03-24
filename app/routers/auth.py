"""Auth router — POST /auth/login, POST /auth/register"""
from __future__ import annotations

import secrets
from fastapi import APIRouter, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

# Demo user store — replace with DB-backed impl in production
_USERS: dict[str, str] = {"admin": "admin123"}
_TOKENS: dict[str, str] = {}  # token -> username


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str


@router.post("/login", response_model=AuthResponse)
async def login(req: AuthRequest) -> AuthResponse:
    stored = _USERS.get(req.username)
    if not stored or stored != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(32)
    _TOKENS[token] = req.username
    return AuthResponse(token=token, username=req.username)


@router.post("/register", response_model=AuthResponse)
async def register(req: AuthRequest) -> AuthResponse:
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if req.username in _USERS:
        raise HTTPException(status_code=409, detail="Username already exists")
    _USERS[req.username] = req.password
    token = secrets.token_hex(32)
    _TOKENS[token] = req.username
    return AuthResponse(token=token, username=req.username)


def get_username_from_token(token: str) -> str | None:
    """Utility for other routers to validate Bearer tokens."""
    return _TOKENS.get(token)
