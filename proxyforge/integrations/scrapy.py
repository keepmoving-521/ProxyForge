"""Scrapy 下载器中间件集成。"""

from __future__ import annotations

import logging
import time
from typing import Any

from proxyforge.lease import ProxyLease
from proxyforge.models import Proxy
from proxyforge.pool import ProxyPool

logger = logging.getLogger(__name__)

LEASE_META_KEY = "proxyforge_lease"
RETRY_COUNT_KEY = "_proxyforge_retry_count"
TRIED_PROXIES_KEY = "_proxyforge_tried_proxies"


class ProxyForgeMiddleware:
    """Scrapy 中间件：分配代理租约、上报结果、失败自动换 IP 重试。"""

    def __init__(
        self,
        pool: ProxyPool,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        meta_key: str = "proxyforge_proxy",
        max_retries: int | None = None,
        retry_http_codes: frozenset[int] | None = None,
    ) -> None:
        self.pool = pool
        self.strategy = strategy
        self.tags = tags
        self.meta_key = meta_key
        self.max_retries = (
            max_retries if max_retries is not None else pool.config.max_proxy_retries
        )
        self.retry_http_codes = (
            retry_http_codes
            if retry_http_codes is not None
            else pool.config.retry_http_codes
        )

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
        max_retries = settings.get("PROXYFORGE_MAX_RETRIES")
        retry_codes_raw = settings.get("PROXYFORGE_RETRY_HTTP_CODES")
        retry_http_codes = (
            frozenset(retry_codes_raw) if retry_codes_raw is not None else None
        )

        return cls(
            pool,
            strategy=strategy,
            tags=tags,
            meta_key=meta_key,
            max_retries=max_retries,
            retry_http_codes=retry_http_codes,
        )

    def process_request(self, request: Any, spider: Any) -> None:
        if request.meta.get(LEASE_META_KEY):
            return

        tried = frozenset(request.meta.get(TRIED_PROXIES_KEY, []))
        lease = self.pool.acquire_lease(
            strategy=self.strategy,
            tags=self.tags,
            exclude_keys=tried,
        )
        self._bind_proxy(request, lease)

    def process_response(self, request: Any, response: Any, spider: Any) -> Any:
        lease: ProxyLease | None = request.meta.get(LEASE_META_KEY)
        proxy: Proxy | None = request.meta.get(self.meta_key)
        if proxy is None or lease is None:
            return response

        if self._should_retry(request, response.status):
            return self._retry_with_new_proxy(request, lease)

        start = request.meta.get("_proxyforge_start")
        latency_ms = (time.perf_counter() - start) * 1000 if start else 0.0

        if 200 <= response.status < 400:
            self.pool.report_success(proxy, latency_ms)
        else:
            self.pool.report_failure(proxy)

        self.pool.release_lease(lease)
        return response

    def process_exception(
        self, request: Any, exception: Exception, spider: Any
    ) -> Any:
        lease: ProxyLease | None = request.meta.get(LEASE_META_KEY)
        proxy: Proxy | None = request.meta.get(self.meta_key)
        if proxy is None or lease is None:
            return None

        retry_count = request.meta.get(RETRY_COUNT_KEY, 0)
        if retry_count >= self.max_retries:
            self.pool.report_failure(proxy)
            self.pool.release_lease(lease)
            logger.debug(
                "Proxy %s failed for %s after max retries: %s",
                proxy.key,
                request.url,
                exception,
            )
            return None

        logger.debug(
            "Proxy %s exception for %s, retrying: %s",
            proxy.key,
            request.url,
            exception,
        )
        return self._retry_with_new_proxy(request, lease)

    def _bind_proxy(self, request: Any, lease: ProxyLease) -> None:
        request.meta["proxy"] = lease.proxy.url
        request.meta[self.meta_key] = lease.proxy
        request.meta[LEASE_META_KEY] = lease
        request.meta["download_slot"] = lease.proxy.key
        request.meta["_proxyforge_start"] = time.perf_counter()
        logger.debug("Assigned proxy %s to %s", lease.proxy.key, request.url)

    def _should_retry(self, request: Any, status: int) -> bool:
        retry_count = request.meta.get(RETRY_COUNT_KEY, 0)
        if retry_count >= self.max_retries:
            return False
        return status in self.retry_http_codes

    def _retry_with_new_proxy(self, request: Any, lease: ProxyLease) -> Any:
        self.pool.report_failure(lease.proxy)
        self.pool.release_lease(lease)

        tried = list(request.meta.get(TRIED_PROXIES_KEY, []))
        tried.append(lease.proxy.key)

        new_request = request.copy()
        new_request.meta[RETRY_COUNT_KEY] = request.meta.get(RETRY_COUNT_KEY, 0) + 1
        new_request.meta[TRIED_PROXIES_KEY] = tried
        for key in (
            "proxy",
            self.meta_key,
            LEASE_META_KEY,
            "download_slot",
            "_proxyforge_start",
        ):
            new_request.meta.pop(key, None)
        new_request.dont_filter = True
        return new_request
