"""代理健康检测。"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Iterable

import httpx

from proxyforge.config import ProxyForgeConfig
from proxyforge.health_urls import HealthCheckContext, HealthCheckUrlResolver
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.scoring import ProxyScorer

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HealthCheckSummary:
    """健康检测批次摘要。"""

    checked: int
    skipped: int
    passed: int
    failed: int
    results: dict[str, bool]


class HealthChecker:
    """并发检测代理可用性与响应延迟。"""

    def __init__(
        self,
        config: ProxyForgeConfig | None = None,
        scorer: ProxyScorer | None = None,
    ) -> None:
        self.config = config or ProxyForgeConfig()
        self.scorer = scorer or ProxyScorer(self.config)
        self._url_resolver = HealthCheckUrlResolver(self.config)

    def resolve_url(
        self,
        proxy: Proxy,
        context: HealthCheckContext | None = None,
    ) -> str:
        return self._url_resolver.resolve(proxy, context)

    def unhealthy_recheck_delay(self, proxy: Proxy) -> float:
        """UNHEALTHY 代理的指数退避复检间隔（秒）。"""
        base = self.config.unhealthy_check_interval
        factor = self.config.unhealthy_backoff_factor
        max_interval = self.config.unhealthy_check_max_interval
        exponent = max(proxy.unhealthy_recheck_attempts, 0)
        return min(base * (factor**exponent), max_interval)

    def should_check(self, proxy: Proxy, now: float | None = None) -> bool:
        """根据代理状态与上次检测时间判断是否需要检测。"""
        current = now if now is not None else time.time()

        if proxy.last_check_at is None:
            return True

        elapsed = current - proxy.last_check_at

        if proxy.status == ProxyStatus.BANNED:
            if proxy.banned_at is None:
                return elapsed >= self.config.banned_check_interval
            if current - proxy.banned_at < self.config.banned_cooldown_seconds:
                return False
            return elapsed >= self.config.banned_check_interval

        if proxy.status == ProxyStatus.UNHEALTHY:
            return elapsed >= self.unhealthy_recheck_delay(proxy)

        return elapsed >= self.config.health_check_interval

    def filter_due_proxies(
        self,
        proxies: Iterable[Proxy],
        *,
        force: bool = False,
    ) -> tuple[list[Proxy], int]:
        if force:
            proxy_list = list(proxies)
            return proxy_list, 0

        due: list[Proxy] = []
        skipped = 0
        now = time.time()
        for proxy in proxies:
            if self.should_check(proxy, now):
                due.append(proxy)
            else:
                skipped += 1
        return due, skipped

    async def check_one(
        self,
        proxy: Proxy,
        client: httpx.AsyncClient,
        *,
        context: HealthCheckContext | None = None,
    ) -> bool:
        headers = {"User-Agent": self.config.user_agent}
        check_url = self.resolve_url(proxy, context)
        was_unhealthy = proxy.status == ProxyStatus.UNHEALTHY
        try:
            start = time.perf_counter()
            response = await client.get(
                check_url,
                headers=headers,
                proxy=proxy.url,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            ok = response.status_code == 200
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("Health check failed for %s: %s", proxy.key, exc)
            ok = False
            latency_ms = 0.0

        if ok:
            proxy.record_success(latency_ms)
            if was_unhealthy:
                logger.info("Proxy %s recovered from UNHEALTHY", proxy.key)
        else:
            proxy.record_failure(
                max_consecutive_failures=self.config.max_consecutive_failures
            )
            if proxy.status == ProxyStatus.UNHEALTHY:
                delay = self.unhealthy_recheck_delay(proxy)
                logger.debug(
                    "Proxy %s still UNHEALTHY, next recheck in %.0fs",
                    proxy.key,
                    delay,
                )

        self.scorer.update_after_check(proxy, ok)
        return ok

    async def _check_batch(
        self,
        client: httpx.AsyncClient,
        batch: list[Proxy],
        concurrency: int,
        *,
        context: HealthCheckContext | None = None,
    ) -> dict[str, bool]:
        semaphore = asyncio.Semaphore(concurrency)
        results: dict[str, bool] = {}

        async def _check(proxy: Proxy) -> None:
            async with semaphore:
                results[proxy.key] = await self.check_one(
                    proxy, client, context=context
                )

        await asyncio.gather(*(_check(p) for p in batch))
        return results

    async def check_all(
        self,
        proxies: Iterable[Proxy],
        *,
        concurrency: int | None = None,
        batch_size: int | None = None,
        force: bool = False,
        context: HealthCheckContext | None = None,
    ) -> HealthCheckSummary:
        concurrency = concurrency or self.config.health_check_concurrency
        batch_size = batch_size or self.config.health_check_batch_size

        all_proxies = list(proxies)
        due_proxies, skipped = self.filter_due_proxies(all_proxies, force=force)

        if not due_proxies:
            logger.debug("Health check skipped %d proxies (not due)", skipped)
            return HealthCheckSummary(
                checked=0,
                skipped=skipped,
                passed=0,
                failed=0,
                results={},
            )

        limits = httpx.Limits(
            max_connections=concurrency,
            max_keepalive_connections=min(concurrency, 20),
        )
        timeout = httpx.Timeout(self.config.health_check_timeout)
        results: dict[str, bool] = {}

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
        ) as client:
            for offset in range(0, len(due_proxies), batch_size):
                batch = due_proxies[offset : offset + batch_size]
                batch_results = await self._check_batch(
                    client, batch, concurrency, context=context
                )
                results.update(batch_results)
                logger.debug(
                    "Health check batch %d-%d complete",
                    offset + 1,
                    offset + len(batch),
                )

        passed = sum(1 for ok in results.values() if ok)
        failed = len(results) - passed
        logger.info(
            "Health check done: checked=%d skipped=%d passed=%d failed=%d",
            len(results),
            skipped,
            passed,
            failed,
        )
        return HealthCheckSummary(
            checked=len(results),
            skipped=skipped,
            passed=passed,
            failed=failed,
            results=results,
        )
