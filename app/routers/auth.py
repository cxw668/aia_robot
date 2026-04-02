"""Auth router — POST /auth/login, POST /auth/register (DB-backed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User, get_db
from app.env_loader import EnvLoader

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7
JWT_SECRET_KEY = EnvLoader.get("JWT_SECRET_KEY", "aia-robot-dev-secret") or "aia-robot-dev-secret"


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str

def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _create_token(user: User) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user.username,
        "uid": user.id,
        "exp": expire_at,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/login", response_model=AuthResponse)
async def login(req: AuthRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    user = await _get_user_by_username(db, req.username)
    if not user or not _verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(user)
    return AuthResponse(token=token, username=user.username)


@router.post("/register", response_model=AuthResponse)
async def register(req: AuthRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password required")

    existed = await _get_user_by_username(db, req.username)
    if existed:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=req.username,
        password_hash=_hash_password(req.password),
    )
    db.add(user)
    await db.flush()

    token = _create_token(user)
    return AuthResponse(token=token, username=user.username)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("uid")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user = await _get_user_by_id(db, int(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def get_username_from_token(token: str) -> str | None:
    """Utility for compatibility with existing imports/tests."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
