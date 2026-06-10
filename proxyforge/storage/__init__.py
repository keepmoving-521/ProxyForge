"""代理池持久化存储。"""

from proxyforge.storage.base import BaseStorage
from proxyforge.storage.redis import RedisStorage

__all__ = ["BaseStorage", "RedisStorage"]
