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

logger = logging.getLogger(__name__)


class ProxyPool:
    """代理池：聚合、检测、评分与调度。"""

    def __init__(
        self,
        config: ProxyForgeConfig | None = None,
        *,
        providers: Iterable[BaseProvider] | None = None,
    ) -> None:
        self.config = config or ProxyForgeConfig()
        self._proxies: dict[str, Proxy] = {}
        self._providers: list[BaseProvider] = list(providers or [])
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
        self._proxies[proxy.key] = proxy

    def add_proxies(self, proxies: Iterable[Proxy]) -> int:
        added = 0
        for proxy in proxies:
            if proxy.key not in self._proxies:
                added += 1
            self._proxies[proxy.key] = proxy
        return added

    def remove_proxy(self, key: str) -> bool:
        return self._proxies.pop(key, None) is not None

    def get(self, key: str) -> Proxy | None:
        return self._proxies.get(key)

    def add_provider(self, provider: BaseProvider) -> None:
        self._providers.append(provider)

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
        return total

    async def check_health(self, *, concurrency: int = 20) -> dict[str, bool]:
        return await self._checker.check_all(self._proxies.values(), concurrency=concurrency)

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

    def report_failure(self, proxy: Proxy) -> None:
        proxy.record_failure()
        self._scorer.update_after_check(proxy, False)

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
