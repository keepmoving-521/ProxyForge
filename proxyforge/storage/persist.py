"""持久化批量 flush 队列。"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Iterable

from proxyforge.models import Proxy
from proxyforge.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class PersistBuffer:
    """线程安全的脏数据缓冲，支持异步批量 flush 与同步 fallback。"""

    def __init__(
        self,
        storage: BaseStorage,
        *,
        batch_size: int = 10,
        sync_fallback: bool = True,
    ) -> None:
        self._storage = storage
        self._batch_size = batch_size
        self._sync_fallback = sync_fallback
        self._dirty: dict[str, Proxy] = {}
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task | None = None

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._dirty)

    def mark_dirty(self, proxy: Proxy) -> None:
        batch_full = False
        with self._lock:
            self._dirty[proxy.key] = proxy
            batch_full = len(self._dirty) >= self._batch_size

        if self._has_running_loop():
            self._schedule_async_flush(force=batch_full)
            return

        if self._sync_fallback and self._storage.supports_sync():
            self.flush_sync()

    def mark_all(self, proxies: Iterable[Proxy]) -> None:
        with self._lock:
            for proxy in proxies:
                self._dirty[proxy.key] = proxy

        if self._has_running_loop():
            self._schedule_async_flush(force=True)
            return

        if self._sync_fallback and self._storage.supports_sync():
            self.flush_sync()

    def _pop_dirty(self) -> list[Proxy]:
        with self._lock:
            batch = list(self._dirty.values())
            self._dirty.clear()
            return batch

    def _schedule_async_flush(self, *, force: bool = False) -> None:
        if not self._has_running_loop():
            return

        if not force and self.pending_count < self._batch_size:
            if self._flush_task and not self._flush_task.done():
                return

        if self._flush_task and not self._flush_task.done():
            return

        loop = asyncio.get_running_loop()
        self._flush_task = loop.create_task(self.flush_async())

    @staticmethod
    def _has_running_loop() -> bool:
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    async def flush_async(self) -> int:
        batch = self._pop_dirty()
        if not batch:
            return 0
        await self._storage.save_proxies_batch(batch)
        logger.debug("Persisted %d proxies via async batch flush", len(batch))
        return len(batch)

    def flush_sync(self) -> int:
        batch = self._pop_dirty()
        if not batch:
            return 0
        self._storage.save_proxies_sync(batch)
        logger.debug("Persisted %d proxies via sync batch flush", len(batch))
        return len(batch)
