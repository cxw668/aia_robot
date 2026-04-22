"""Auth router — POST /auth/login, POST /auth/register (DB-backed)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_security import FailedLoginTracker
from app.database import User, get_db
from app.config import settings
from app.rate_limit import build_rate_limit_dependency
from app.request_context import get_request_id

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7
JWT_SECRET_KEYS = tuple(settings.jwt_secret_keys)
failed_login_tracker = FailedLoginTracker(
    max_failures=settings.auth_login_failure_threshold,
    window_seconds=settings.auth_login_failure_window_seconds,
    lockout_seconds=settings.auth_login_lockout_seconds,
)


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str


auth_rate_limit = build_rate_limit_dependency(
    scope="auth",
    limit=settings.auth_rate_limit_count,
    window_seconds=settings.auth_rate_limit_window_seconds,
    message="Too many authentication attempts. Please try again later.",
)


def _validate_password_strength(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if not re.search(r"[A-Za-z]", password):
        return "Password must include at least one letter"
    if not re.search(r"\d", password):
        return "Password must include at least one number"
    return None


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _normalize_username_key(username: str) -> str:
    return username.strip().lower()


def _build_login_lockout_exception(retry_after_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "message": "Too many failed login attempts. Please try again later.",
            "details": {"retry_after_seconds": retry_after_seconds},
        },
    )


def _create_token(user: User) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user.username,
        "uid": user.id,
        "exp": expire_at,
    }
    return jwt.encode(payload, JWT_SECRET_KEYS[0], algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    last_error: JWTError | None = None
    for secret in JWT_SECRET_KEYS:
        try:
            return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        except JWTError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise JWTError("JWT secret keys are not configured")


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/login", response_model=AuthResponse)
async def login(
    req: AuthRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(auth_rate_limit),
) -> AuthResponse:
    username_key = _normalize_username_key(req.username)
    retry_after_seconds = failed_login_tracker.get_retry_after(username_key)
    if retry_after_seconds > 0:
        logger.warning(
            "[auth] login blocked | request_id=%s | username=%s | retry_after_seconds=%s",
            get_request_id(),
            req.username,
            retry_after_seconds,
        )
        raise _build_login_lockout_exception(retry_after_seconds)

    user = await _get_user_by_username(db, req.username)
    if not user or not _verify_password(req.password, user.password_hash):
        logger.warning("[auth] login failed | request_id=%s | username=%s", get_request_id(), req.username)
        retry_after_seconds = failed_login_tracker.record_failure(username_key)
        if retry_after_seconds > 0:
            logger.warning(
                "[auth] login locked | request_id=%s | username=%s | retry_after_seconds=%s",
                get_request_id(),
                req.username,
                retry_after_seconds,
            )
            raise _build_login_lockout_exception(retry_after_seconds)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    failed_login_tracker.reset(username_key)
    token = _create_token(user)
    logger.info("[auth] login succeeded | request_id=%s | username=%s", get_request_id(), user.username)
    return AuthResponse(token=token, username=user.username)


@router.post("/register", response_model=AuthResponse)
async def register(
    req: AuthRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(auth_rate_limit),
) -> AuthResponse:
    if not req.username or not req.password:
        logger.warning("[auth] register rejected | request_id=%s | reason=missing_fields", get_request_id())
        raise HTTPException(status_code=400, detail="Username and password required")

    password_error = _validate_password_strength(req.password)
    if password_error:
        logger.warning("[auth] register rejected | request_id=%s | username=%s | reason=weak_password", get_request_id(), req.username)
        raise HTTPException(status_code=400, detail=password_error)

    existed = await _get_user_by_username(db, req.username)
    if existed:
        logger.warning("[auth] register rejected | request_id=%s | username=%s | reason=duplicate_username", get_request_id(), req.username)
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=req.username,
        password_hash=_hash_password(req.password),
    )
    db.add(user)
    await db.flush()

    token = _create_token(user)
    logger.info("[auth] register succeeded | request_id=%s | username=%s", get_request_id(), user.username)
    return AuthResponse(token=token, username=user.username)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    try:
        payload = _decode_token(token)
        user_id = payload.get("uid")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user = await _get_user_by_id(db, int(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    current_user: User = Depends(get_current_user),
    _: None = Depends(auth_rate_limit),
) -> AuthResponse:
    token = _create_token(current_user)
    logger.info("[auth] token refreshed | request_id=%s | username=%s", get_request_id(), current_user.username)
    return AuthResponse(token=token, username=current_user.username)


def get_username_from_token(token: str) -> str | None:
    """Utility for compatibility with existing imports/tests."""
    try:
        payload = _decode_token(token)
        return payload.get("sub")
    except JWTError:
        return None
