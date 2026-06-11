"""代理池核心管理。"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from proxyforge.config import ProxyForgeConfig
from proxyforge.health import HealthChecker
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.providers.base import BaseProvider
from proxyforge.router import ProxyRouter
from proxyforge.scoring import ProxyScorer
from proxyforge.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class ProxyPool:
    """代理池：聚合、检测、评分与调度。"""

    def __init__(
        self,
        config: ProxyForgeConfig | None = None,
        *,
        providers: Iterable[BaseProvider] | None = None,
        storage: BaseStorage | None = None,
        auto_persist: bool = False,
    ) -> None:
        self.config = config or ProxyForgeConfig()
        self._proxies: dict[str, Proxy] = {}
        self._providers: list[BaseProvider] = list(providers or [])
        self._storage = storage
        self._auto_persist = auto_persist
        self._scorer = ProxyScorer(self.config)
        self._checker = HealthChecker(self.config, self._scorer)
        self._router = ProxyRouter(self.config)
        self._health_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def proxies(self) -> list[Proxy]:
        return list(self._proxies.values())

    @property
    def healthy_count(self) -> int:
        return sum(1 for p in self._proxies.values() if p.status == ProxyStatus.HEALTHY)

    @property
    def total_count(self) -> int:
        return len(self._proxies)

    def add_proxy(self, proxy: Proxy) -> None:
        existing = self._proxies.get(proxy.key)
        if existing is None:
            self._proxies[proxy.key] = proxy
        else:
            self._merge_proxy(existing, proxy)

    def add_proxies(self, proxies: Iterable[Proxy]) -> int:
        added = 0
        for proxy in proxies:
            if proxy.key not in self._proxies:
                added += 1
            self.add_proxy(proxy)
        return added

    @staticmethod
    def _merge_proxy(existing: Proxy, incoming: Proxy) -> None:
        """合并 Provider 数据，保留运行时统计。"""
        existing.host = incoming.host
        existing.port = incoming.port
        existing.protocol = incoming.protocol
        existing.username = incoming.username
        existing.password = incoming.password
        existing.provider = incoming.provider
        existing.tags = existing.tags | incoming.tags
        existing.metadata = {**existing.metadata, **incoming.metadata}

    def remove_proxy(self, key: str) -> bool:
        return self._proxies.pop(key, None) is not None

    def get(self, key: str) -> Proxy | None:
        return self._proxies.get(key)

    def add_provider(self, provider: BaseProvider) -> None:
        self._providers.append(provider)

    async def load(self) -> int:
        """从持久化存储加载代理池。"""
        if self._storage is None:
            return 0
        proxies = await self._storage.load_all()
        count = self.add_proxies(proxies)
        logger.info("Loaded %d proxies from storage", count)
        return count

    async def persist(self) -> None:
        """将当前代理池持久化。"""
        if self._storage is None:
            return
        await self._storage.save_all(self._proxies.values())
        logger.debug("Persisted %d proxies to storage", self.total_count)

    async def _maybe_persist(self, proxy: Proxy | None = None) -> None:
        if not self._auto_persist or self._storage is None:
            return
        if proxy is not None:
            await self._storage.save_proxy(proxy)
        else:
            await self.persist()

    async def refresh_from_providers(self) -> int:
        """从所有已注册服务商拉取并合并代理。"""
        total = 0
        async with self._lock:
            for provider in self._providers:
                try:
                    fetched = await provider.fetch_proxies()
                    total += self.add_proxies(fetched)
                    logger.info(
                        "Fetched %d proxies from provider %s",
                        len(fetched),
                        provider.name,
                    )
                except Exception:
                    logger.exception("Failed to fetch from provider %s", provider.name)
        await self._maybe_persist()
        return total

    async def check_health(self, *, concurrency: int = 20) -> dict[str, bool]:
        results = await self._checker.check_all(
            self._proxies.values(), concurrency=concurrency
        )
        await self._maybe_persist()
        return results

    async def start_background_health_check(self) -> None:
        if self._health_task and not self._health_task.done():
            return

        async def _loop() -> None:
            while True:
                try:
                    await self.check_health()
                except Exception:
                    logger.exception("Background health check failed")
                await asyncio.sleep(self.config.health_check_interval)

        self._health_task = asyncio.create_task(_loop())

    async def stop_background_health_check(self) -> None:
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

    def acquire(
        self,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
    ) -> Proxy:
        """获取一个可用代理。"""
        proxies = self._proxies.values()
        if strategy == "best":
            return self._router.select_best(proxies, tags=tags)
        if strategy == "round_robin":
            return self._router.select_round_robin(proxies, tags=tags)
        return self._router.select_weighted_random(proxies, tags=tags)

    def report_success(self, proxy: Proxy, latency_ms: float) -> None:
        proxy.record_success(latency_ms)
        self._scorer.update_after_check(proxy, True)
        self._schedule_persist(proxy)

    def report_failure(self, proxy: Proxy) -> None:
        proxy.record_failure(
            max_consecutive_failures=self.config.max_consecutive_failures
        )
        self._scorer.update_after_check(proxy, False)
        self._schedule_persist(proxy)

    def _schedule_persist(self, proxy: Proxy | None = None) -> None:
        if not self._auto_persist or self._storage is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if proxy is not None:
            loop.create_task(self._storage.save_proxy(proxy))
        else:
            loop.create_task(self.persist())

    def stats(self) -> dict:
        by_status: dict[str, int] = {}
        for proxy in self._proxies.values():
            by_status[proxy.status.value] = by_status.get(proxy.status.value, 0) + 1
        scores = [p.score for p in self._proxies.values()]
        return {
            "total": self.total_count,
            "healthy": self.healthy_count,
            "by_status": by_status,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
        }
