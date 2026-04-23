from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import app.main as main_module
import app.routers.auth as auth_router
import app.routers.chat as chat_router
from app.database import ChatMessage, ChatSession, User


@dataclass
class FakeAsyncSession:
    users_by_username: dict[str, User] = field(default_factory=dict)
    users_by_id: dict[int, User] = field(default_factory=dict)
    chat_sessions: dict[str, ChatSession] = field(default_factory=dict)
    chat_messages: dict[str, list[ChatMessage]] = field(default_factory=dict)
    _next_user_id: int = 1
    _next_message_id: int = 1

    def add(self, instance: object) -> None:
        if isinstance(instance, User):
            if instance.id is None:
                instance.id = self._next_user_id
                self._next_user_id += 1
            self.users_by_username[instance.username] = instance
            self.users_by_id[int(instance.id)] = instance
            return

        if isinstance(instance, ChatSession):
            self.chat_sessions[instance.id] = instance
            self.chat_messages.setdefault(instance.id, [])
            return

        if isinstance(instance, ChatMessage):
            if instance.id is None:
                instance.id = self._next_message_id
                self._next_message_id += 1
            self.chat_messages.setdefault(instance.session_id, []).append(instance)
            return

        raise TypeError(f"Unsupported model for fake session: {type(instance)!r}")

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def delete(self, instance: object) -> None:
        if not isinstance(instance, ChatSession):
            raise TypeError(f"Unsupported delete model for fake session: {type(instance)!r}")
        self.chat_sessions.pop(instance.id, None)
        self.chat_messages.pop(instance.id, None)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_user(
    client: TestClient,
    *,
    username: str = "alice",
    password: str = "abc12345",
) -> str:
    response = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["token"]


@contextmanager
def create_test_client(
    db: FakeAsyncSession,
    *,
    retrieve_docs: list[dict] | Callable[..., list[dict]] | None = None,
    chat_answer: str = "这是测试回答。",
    stream_chunks: list[str] | None = None,
    cached_turn: dict | None = None,
) -> Iterator[TestClient]:
    async def override_get_db() -> AsyncIterator[FakeAsyncSession]:
        yield db

    async def noop_dependency() -> None:
        return None

    async def fake_get_user_by_username(_: object, username: str) -> User | None:
        return db.users_by_username.get(username)

    async def fake_get_user_by_id(_: object, user_id: int) -> User | None:
        user = db.users_by_id.get(user_id)
        if not user or user.is_active is False:
            return None
        return user

    async def fake_get_user_session(_: object, user_id: int, session_id: str) -> ChatSession | None:
        session = db.chat_sessions.get(session_id)
        if not session or session.user_id != user_id:
            return None
        return session

    async def fake_load_session_messages(_: object, session_id: str) -> list[ChatMessage]:
        return list(db.chat_messages.get(session_id, []))

    with ExitStack() as stack:
        stack.enter_context(patch.object(main_module, "init_db", new=AsyncMock(return_value=None)))
        stack.enter_context(
            patch.object(main_module, "recover_interrupted_ingest_jobs", new=AsyncMock(return_value=0))
        )
        stack.enter_context(patch.object(main_module, "start_ingest_worker", new=AsyncMock(return_value=None)))
        stack.enter_context(patch.object(main_module, "stop_ingest_worker", new=AsyncMock(return_value=None)))
        stack.enter_context(patch.object(main_module, "ping_redis", new=AsyncMock(return_value=True)))
        stack.enter_context(patch.object(auth_router, "_get_user_by_username", new=fake_get_user_by_username))
        stack.enter_context(patch.object(auth_router, "_get_user_by_id", new=fake_get_user_by_id))
        stack.enter_context(patch.object(chat_router, "_get_user_session", new=fake_get_user_session))
        stack.enter_context(patch.object(chat_router, "_load_session_messages", new=fake_load_session_messages))
        if callable(retrieve_docs):
            stack.enter_context(patch.object(chat_router, "retrieve", side_effect=retrieve_docs))
        else:
            stack.enter_context(
                patch.object(chat_router, "retrieve", return_value=list(retrieve_docs or []))
            )
        stack.enter_context(patch.object(chat_router, "chat_completion", return_value=chat_answer))
        stack.enter_context(
            patch.object(chat_router, "chat_completion_stream", return_value=iter(stream_chunks or [chat_answer]))
        )
        stack.enter_context(
            patch.object(chat_router, "cache_get_json", new=AsyncMock(return_value=cached_turn))
        )
        stack.enter_context(
            patch.object(chat_router, "cache_set_json", new=AsyncMock(return_value=True))
        )

        main_module.app.dependency_overrides[auth_router.get_db] = override_get_db
        main_module.app.dependency_overrides[chat_router.get_db] = override_get_db
        main_module.app.dependency_overrides[auth_router.auth_rate_limit] = noop_dependency
        main_module.app.dependency_overrides[chat_router.chat_rate_limit] = noop_dependency

        try:
            with TestClient(main_module.app) as client:
                yield client
        finally:
            main_module.app.dependency_overrides.clear()
