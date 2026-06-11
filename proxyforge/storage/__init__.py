"""代理池持久化存储。"""

from proxyforge.storage.base import BaseStorage
from proxyforge.storage.persist import PersistBuffer
from proxyforge.storage.redis import RedisStorage
from proxyforge.storage.redis_coordinator import RedisLeaseCoordinator

__all__ = ["BaseStorage", "PersistBuffer", "RedisLeaseCoordinator", "RedisStorage"]
