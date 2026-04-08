
"""应用主包初始化。

此模块负责对外暴露 `app` 包的常用子模块与工厂函数，便于在
项目其他位置统一通过 `import app` 访问配置、数据库、缓存等核心
功能。同时在此处添加中文注释以便维护。
"""

from __future__ import annotations

# 将常用模块在包顶层导出，方便交互式导入和测试：
from .config import settings  # 应用配置
from .database import engine, AsyncSessionLocal, get_db  # 数据库引擎与依赖
from .cache import get_redis_client, get_redis, ping_redis  # Redis 缓存工具
from .session import store as session_store  # 内存会话存储

__all__ = [
	"settings",
	"engine",
	"AsyncSessionLocal",
	"get_db",
	"get_redis_client",
	"get_redis",
	"ping_redis",
	"session_store",
]


