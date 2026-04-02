from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

class EnvLoader:
    _loaded = False
    _env_path = Path(__file__).resolve().parent.parent / ".env"

    @classmethod
    def load(cls) -> None:
        if cls._loaded:
            return
        load_dotenv(dotenv_path=cls._env_path)
        cls._loaded = True

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str | None:
        cls.load()
        return os.getenv(key, default)
