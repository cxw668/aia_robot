"""会话模块：提供内存会话管理器与会话数据结构。

已从顶级 `app/session.py` 移动至此包。
"""
from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal

ROLE = Literal["user", "assistant", "system"]
MAX_TURNS = 10
SESSION_TTL = 3600


@dataclass
class Message:
    role: ROLE
    content: str


@dataclass
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add(self, role: ROLE, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        self.updated_at = time.time()
        self._trim()

    def _trim(self) -> None:
        system = [m for m in self.messages if m.role == "system"]
        turns = [m for m in self.messages if m.role != "system"]
        if len(turns) > MAX_TURNS * 2:
            turns = turns[-(MAX_TURNS * 2):]
        self.messages = system + turns

    def to_openai_messages(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def is_expired(self) -> bool:
        return (time.time() - self.updated_at) > SESSION_TTL


class SessionStore:
    def __init__(self, max_sessions: int = 1000) -> None:
        self._store: OrderedDict[str, Session] = OrderedDict()
        self._max = max_sessions

    def get_or_create(self, session_id: str | None) -> Session:
        sid = session_id or str(uuid.uuid4())
        if sid in self._store:
            self._store.move_to_end(sid)
            sess = self._store[sid]
            if sess.is_expired():
                sess.messages.clear()
                sess.created_at = time.time()
            return sess
        sess = Session(session_id=sid)
        self._store[sid] = sess
        self._evict()
        return sess

    def get(self, session_id: str) -> Session | None:
        return self._store.get(session_id)

    def delete(self, session_id: str) -> bool:
        return bool(self._store.pop(session_id, None))

    def _evict(self) -> None:
        while len(self._store) > self._max:
            self._store.popitem(last=False)


store = SessionStore()
