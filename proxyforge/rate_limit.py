"""单 IP 请求限流（QPS / 并发连接）。"""

from __future__ import annotations

import threading
import time


class ProxyRateLimiter:
    """按 proxy key 限制 QPS 与并发连接数。"""

    def __init__(
        self,
        *,
        max_qps: float = 0.0,
        max_concurrent: int = 0,
    ) -> None:
        self.max_qps = max(0.0, max_qps)
        self.max_concurrent = max(0, max_concurrent)
        self._lock = threading.Lock()
        self._concurrent: dict[str, int] = {}
        self._request_times: dict[str, list[float]] = {}

    @property
    def enabled(self) -> bool:
        return self.max_qps > 0 or self.max_concurrent > 0

    def is_at_capacity(self, proxy_key: str) -> bool:
        """是否已达 QPS 或并发上限（不占用配额）。"""
        if not self.enabled:
            return False
        with self._lock:
            return self._is_at_capacity_locked(proxy_key)

    def try_acquire(self, proxy_key: str) -> bool:
        """占用一次 QPS 配额并增加并发计数。"""
        if not self.enabled:
            return True
        with self._lock:
            if self._is_at_capacity_locked(proxy_key):
                return False
            if self.max_qps > 0:
                now = time.time()
                times = self._prune_times_locked(proxy_key, now)
                times.append(now)
                self._request_times[proxy_key] = times
            if self.max_concurrent > 0:
                self._concurrent[proxy_key] = self._concurrent.get(proxy_key, 0) + 1
            return True

    def release(self, proxy_key: str) -> None:
        """请求结束后释放并发计数（QPS 窗口按时间自然过期）。"""
        if self.max_concurrent <= 0:
            return
        with self._lock:
            count = self._concurrent.get(proxy_key, 0)
            if count <= 1:
                self._concurrent.pop(proxy_key, None)
            else:
                self._concurrent[proxy_key] = count - 1

    def active_concurrent(self, proxy_key: str) -> int:
        with self._lock:
            return self._concurrent.get(proxy_key, 0)

    def _prune_times_locked(self, proxy_key: str, now: float) -> list[float]:
        times = self._request_times.get(proxy_key, [])
        times = [t for t in times if now - t < 1.0]
        if times:
            self._request_times[proxy_key] = times
        else:
            self._request_times.pop(proxy_key, None)
        return times

    def _is_at_capacity_locked(self, proxy_key: str) -> bool:
        if self.max_concurrent > 0:
            if self._concurrent.get(proxy_key, 0) >= self.max_concurrent:
                return True
        if self.max_qps > 0:
            now = time.time()
            times = self._prune_times_locked(proxy_key, now)
            if len(times) >= int(self.max_qps):
                return True
        return False
