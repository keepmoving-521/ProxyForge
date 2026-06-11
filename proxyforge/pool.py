"""代理池核心管理。"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Iterable

from proxyforge.config import ProxyForgeConfig
from proxyforge.health import HealthChecker
from proxyforge.health_urls import HealthCheckContext
from proxyforge.lease import LeaseManager, ProxyLease
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.providers.base import BaseProvider
from proxyforge.router import ProxyRouter
from proxyforge.scoring import ProxyScorer
from proxyforge.storage.base import BaseStorage
from proxyforge.storage.persist import PersistBuffer

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
        self._persist_buffer: PersistBuffer | None = None
        if storage is not None and auto_persist:
            self._persist_buffer = PersistBuffer(
                storage,
                batch_size=self.config.persist_batch_size,
                sync_fallback=self.config.persist_sync_fallback,
            )
        self._scorer = ProxyScorer(self.config)
        self._checker = HealthChecker(self.config, self._scorer)
        self._router = ProxyRouter(self.config)
        self._lease_manager = LeaseManager(
            ttl_seconds=self.config.lease_ttl_seconds,
            max_per_proxy=self.config.max_leases_per_proxy,
        )
        self._health_task: asyncio.Task | None = None
        self._health_check_context: HealthCheckContext | None = None
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

    @property
    def proxies(self) -> list[Proxy]:
        return list(self._proxies.values())

    @property
    def healthy_count(self) -> int:
        return sum(1 for p in self._proxies.values() if p.status == ProxyStatus.HEALTHY)

    @property
    def total_count(self) -> int:
        return len(self._proxies)

    @property
    def active_leases(self) -> int:
        return self._lease_manager.active_count()

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
        if self._persist_buffer is not None:
            self._persist_buffer.mark_all(self._proxies.values())
            await self._persist_buffer.flush_async()
        else:
            await self._storage.save_all(self._proxies.values())
        logger.debug("Persisted %d proxies to storage", self.total_count)

    async def flush_persist(self) -> int:
        """立即 flush 待持久化的脏数据。"""
        if self._persist_buffer is None:
            return 0
        return await self._persist_buffer.flush_async()

    def flush_persist_sync(self) -> int:
        """同步 flush 待持久化的脏数据（适用于 Scrapy 等无事件循环场景）。"""
        if self._persist_buffer is None:
            return 0
        return self._persist_buffer.flush_sync()

    async def _maybe_persist(self, proxy: Proxy | None = None) -> None:
        if not self._auto_persist or self._storage is None:
            return
        if self._persist_buffer is None:
            if proxy is not None:
                await self._storage.save_proxy(proxy)
            else:
                await self.persist()
            return
        if proxy is not None:
            self._persist_buffer.mark_dirty(proxy)
        else:
            self._persist_buffer.mark_all(self._proxies.values())
        await self._persist_buffer.flush_async()

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

    async def check_health(
        self,
        *,
        task: str | None = None,
        spider: str | None = None,
        tags: frozenset[str] | None = None,
        concurrency: int | None = None,
        batch_size: int | None = None,
        force: bool = False,
    ) -> dict[str, bool]:
        context = self._build_health_context(task=task, spider=spider, tags=tags)
        summary = await self._checker.check_all(
            self._proxies.values(),
            concurrency=concurrency,
            batch_size=batch_size,
            force=force,
            context=context,
        )
        await self._maybe_persist()
        return summary.results

    def resolve_health_check_url(
        self,
        proxy: Proxy,
        *,
        task: str | None = None,
        spider: str | None = None,
        tags: frozenset[str] | None = None,
    ) -> str:
        context = self._build_health_context(task=task, spider=spider, tags=tags)
        return self._checker.resolve_url(proxy, context)

    @staticmethod
    def _build_health_context(
        *,
        task: str | None = None,
        spider: str | None = None,
        tags: frozenset[str] | None = None,
    ) -> HealthCheckContext | None:
        if task is None and spider is None and tags is None:
            return None
        return HealthCheckContext(task=task, spider=spider, tags=tags)

    async def start_background_health_check(
        self,
        *,
        task: str | None = None,
        spider: str | None = None,
        tags: frozenset[str] | None = None,
    ) -> None:
        if self._health_task and not self._health_task.done():
            return

        self._health_check_context = self._build_health_context(
            task=task, spider=spider, tags=tags
        )

        async def _loop() -> None:
            while True:
                try:
                    await self.check_health(
                        task=task,
                        spider=spider,
                        tags=tags,
                    )
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

    def _select_proxy(
        self,
        *,
        strategy: str,
        tags: frozenset[str] | None,
        exclude_keys: frozenset[str] | None,
    ) -> Proxy:
        proxies = self._proxies.values()
        leased = self._lease_manager.get_excluded_keys()
        combined_exclude = leased
        if exclude_keys:
            combined_exclude = leased | exclude_keys

        if strategy == "best":
            return self._router.select_best(
                proxies, tags=tags, exclude_keys=combined_exclude
            )
        if strategy == "round_robin":
            return self._router.select_round_robin(
                proxies, tags=tags, exclude_keys=combined_exclude
            )
        return self._router.select_weighted_random(
            proxies, tags=tags, exclude_keys=combined_exclude
        )

    def acquire(
        self,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
    ) -> Proxy:
        """获取一个可用代理（不创建租约）。"""
        with self._sync_lock:
            return self._select_proxy(
                strategy=strategy, tags=tags, exclude_keys=exclude_keys
            )

    def acquire_lease(
        self,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
    ) -> ProxyLease:
        """获取代理并创建租约，防止并发重复使用。"""
        with self._sync_lock:
            proxy = self._select_proxy(
                strategy=strategy, tags=tags, exclude_keys=exclude_keys
            )
            if self.config.lease_enabled:
                return self._lease_manager.create(proxy)
            return ProxyLease(
                lease_id="",
                proxy=proxy,
                created_at=0.0,
                ttl_seconds=0.0,
            )

    def release_lease(self, lease: ProxyLease | str | None) -> None:
        """释放代理租约。"""
        if lease is None:
            return
        if isinstance(lease, ProxyLease) and not lease.lease_id:
            return
        with self._sync_lock:
            self._lease_manager.release(lease)

    def report_success(self, proxy: Proxy, latency_ms: float) -> None:
        with self._sync_lock:
            proxy.record_success(latency_ms)
            self._scorer.update_after_check(proxy, True)
        self._schedule_persist(proxy)

    def report_failure(self, proxy: Proxy) -> None:
        with self._sync_lock:
            proxy.record_failure(
                max_consecutive_failures=self.config.max_consecutive_failures
            )
            self._scorer.update_after_check(proxy, False)
        self._schedule_persist(proxy)

    def _schedule_persist(self, proxy: Proxy | None = None) -> None:
        if not self._auto_persist or self._storage is None:
            return
        if self._persist_buffer is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            if proxy is not None:
                loop.create_task(self._storage.save_proxy(proxy))
            else:
                loop.create_task(self.persist())
            return

        if proxy is not None:
            self._persist_buffer.mark_dirty(proxy)
        else:
            self._persist_buffer.mark_all(self._proxies.values())

    def stats(self) -> dict:
        by_status: dict[str, int] = {}
        for proxy in self._proxies.values():
            by_status[proxy.status.value] = by_status.get(proxy.status.value, 0) + 1
        scores = [p.score for p in self._proxies.values()]
        return {
            "total": self.total_count,
            "healthy": self.healthy_count,
            "active_leases": self.active_leases,
            "by_status": by_status,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
        }
