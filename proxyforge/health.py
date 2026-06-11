"""代理健康检测。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Iterable

import httpx

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy
from proxyforge.scoring import ProxyScorer

logger = logging.getLogger(__name__)


class HealthChecker:
    """并发检测代理可用性与响应延迟。"""

    def __init__(
        self,
        config: ProxyForgeConfig | None = None,
        scorer: ProxyScorer | None = None,
    ) -> None:
        self.config = config or ProxyForgeConfig()
        self.scorer = scorer or ProxyScorer(self.config)

    async def check_one(self, proxy: Proxy) -> bool:
        headers = {"User-Agent": self.config.user_agent}
        try:
            async with httpx.AsyncClient(
                proxy=proxy.url,
                timeout=self.config.health_check_timeout,
                follow_redirects=True,
            ) as client:
                start = time.perf_counter()
                response = await client.get(
                    self.config.health_check_url,
                    headers=headers,
                )
                latency_ms = (time.perf_counter() - start) * 1000
                ok = response.status_code == 200
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("Health check failed for %s: %s", proxy.key, exc)
            ok = False
            latency_ms = 0.0

        if ok:
            proxy.record_success(latency_ms)
        else:
            proxy.record_failure(
                max_consecutive_failures=self.config.max_consecutive_failures
            )

        self.scorer.update_after_check(proxy, ok)
        return ok

    async def check_all(
        self,
        proxies: Iterable[Proxy],
        *,
        concurrency: int = 20,
    ) -> dict[str, bool]:
        semaphore = asyncio.Semaphore(concurrency)
        results: dict[str, bool] = {}

        async def _check(proxy: Proxy) -> None:
            async with semaphore:
                results[proxy.key] = await self.check_one(proxy)

        await asyncio.gather(*(_check(p) for p in proxies))
        return results
