"""Scrapy 下载器中间件集成。"""

from __future__ import annotations

import logging
import time
from typing import Any

from proxyforge.models import Proxy
from proxyforge.pool import ProxyPool

logger = logging.getLogger(__name__)


class ProxyForgeMiddleware:
    """Scrapy 中间件：自动分配代理并反馈成功/失败。"""

    def __init__(
        self,
        pool: ProxyPool,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        meta_key: str = "proxyforge_proxy",
    ) -> None:
        self.pool = pool
        self.strategy = strategy
        self.tags = tags
        self.meta_key = meta_key

    @classmethod
    def from_crawler(cls, crawler: Any) -> ProxyForgeMiddleware:
        settings = crawler.settings
        pool = settings.get("PROXYFORGE_POOL")
        if pool is None:
            raise ValueError("Scrapy setting PROXYFORGE_POOL is required")

        strategy = settings.get("PROXYFORGE_STRATEGY", "weighted")
        tags_raw = settings.get("PROXYFORGE_TAGS")
        tags = frozenset(tags_raw) if tags_raw else None
        meta_key = settings.get("PROXYFORGE_META_KEY", "proxyforge_proxy")

        return cls(pool, strategy=strategy, tags=tags, meta_key=meta_key)

    def process_request(self, request: Any, spider: Any) -> None:
        proxy = self.pool.acquire(strategy=self.strategy, tags=self.tags)
        request.meta["proxy"] = proxy.url
        request.meta[self.meta_key] = proxy
        request.meta["download_slot"] = proxy.key
        request.meta["_proxyforge_start"] = time.perf_counter()
        logger.debug("Assigned proxy %s to %s", proxy.key, request.url)

    def process_response(self, request: Any, response: Any, spider: Any) -> Any:
        proxy: Proxy | None = request.meta.get(self.meta_key)
        if proxy is None:
            return response

        start = request.meta.get("_proxyforge_start")
        latency_ms = (time.perf_counter() - start) * 1000 if start else 0.0

        if 200 <= response.status < 400:
            self.pool.report_success(proxy, latency_ms)
        else:
            self.pool.report_failure(proxy)
        return response

    def process_exception(self, request: Any, exception: Exception, spider: Any) -> None:
        proxy: Proxy | None = request.meta.get(self.meta_key)
        if proxy is not None:
            self.pool.report_failure(proxy)
            logger.debug(
                "Proxy %s failed for %s: %s",
                proxy.key,
                request.url,
                exception,
            )
