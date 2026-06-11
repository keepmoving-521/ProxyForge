"""httpx 客户端集成。"""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any

import httpx

from proxyforge.lease import ProxyLease
from proxyforge.pool import ProxyPool

logger = logging.getLogger(__name__)


class ProxyForgeHttpxClient:
    """httpx 封装：自动注入代理租约、失败换 IP 重试、上报结果。"""

    def __init__(
        self,
        pool: ProxyPool,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        max_retries: int | None = None,
        retry_http_codes: frozenset[int] | None = None,
        client: httpx.AsyncClient | None = None,
        **client_kwargs: Any,
    ) -> None:
        self.pool = pool
        self.strategy = strategy
        self.tags = tags
        self.max_retries = (
            max_retries if max_retries is not None else pool.config.max_proxy_retries
        )
        self.retry_http_codes = (
            retry_http_codes
            if retry_http_codes is not None
            else pool.config.retry_http_codes
        )
        self._external_client = client
        self._client = client
        self._client_kwargs = client_kwargs
        self._owns_client = client is None

    async def __aenter__(self) -> ProxyForgeHttpxClient:
        if self._client is None:
            self._client = httpx.AsyncClient(**self._client_kwargs)
            self._owns_client = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ProxyForgeHttpxClient is not started; use async with")
        return self._client

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        tried: set[str] = set()
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            lease: ProxyLease | None = None
            try:
                lease = self.pool.acquire_lease(
                    strategy=self.strategy,
                    tags=self.tags,
                    exclude_keys=frozenset(tried),
                )
                kwargs.setdefault("proxy", lease.proxy.url)
                start = time.perf_counter()
                response = await self.client.request(method, url, **kwargs)
                latency_ms = (time.perf_counter() - start) * 1000

                if response.status_code in self.retry_http_codes:
                    if attempt < self.max_retries:
                        tried.add(lease.proxy.key)
                        self.pool.report_failure(lease.proxy)
                        continue
                    self.pool.report_failure(lease.proxy)
                    return response

                if 200 <= response.status_code < 400:
                    self.pool.report_success(lease.proxy, latency_ms)
                else:
                    self.pool.report_failure(lease.proxy)
                return response

            except (httpx.HTTPError, OSError) as exc:
                last_exc = exc
                if lease is not None:
                    tried.add(lease.proxy.key)
                    self.pool.report_failure(lease.proxy)
                if attempt >= self.max_retries:
                    raise
            finally:
                if lease is not None:
                    self.pool.release_lease(lease)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Request failed without exception")

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)
