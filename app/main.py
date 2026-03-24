"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.cache import ping_redis
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.knowledge import router as kb_router


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

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(kb_router)


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "version": settings.app_version, "status": "running"}
