"""FastAPI application entry point."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.cache import ping_redis
from app.config import settings
from app.database import init_db
from app.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.request_context import reset_request_id, set_request_id
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.knowledge import router as kb_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle handler."""
    # ── Startup ───────────────────────────────────────────────────────────────
    try:
        await init_db()
        print("[startup] MySQL tables initialised.")
    except Exception as exc:
        print(f"[startup] MySQL init warning: {exc}")

    redis_ok = await ping_redis()
    print(f"[startup] Redis ping: {'OK' if redis_ok else 'FAILED — running without cache'}")

    yield

    # ── Shutdown (nothing to tear down for now) ───────────────────────────────


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AIA 智能客服后端 — RAG + 多轮对话",
    lifespan=lifespan,
)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    token = set_request_id(request_id)
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "[api] request completed | request_id=%s | method=%s | path=%s | status=%s | duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            status_code,
            duration_ms,
        )
        reset_request_id(token)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(kb_router)


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "version": settings.app_version, "status": "running"}
