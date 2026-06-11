"""aiohttp 客户端集成。"""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any

from proxyforge.lease import ProxyLease
from proxyforge.pool import ProxyPool

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover - optional dependency
    aiohttp = None  # type: ignore[assignment]


class ProxyForgeClient:
    """aiohttp 封装：自动注入代理租约并上报使用结果。"""

    def __init__(
        self,
        pool: ProxyPool,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        max_retries: int | None = None,
        retry_http_codes: frozenset[int] | None = None,
        session: aiohttp.ClientSession | None = None,
        **session_kwargs: Any,
    ) -> None:
        if aiohttp is None:
            raise ImportError(
                "aiohttp is required for ProxyForgeClient. "
                "Install with: pip install proxyforge[aiohttp]"
            )
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
        self._external_session = session
        self._session = session
        self._session_kwargs = session_kwargs
        self._owns_session = session is None

    async def __aenter__(self) -> ProxyForgeClient:
        if self._session is None:
            self._session = aiohttp.ClientSession(**self._session_kwargs)
            self._owns_session = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("ProxyForgeClient is not started; use async with")
        return self._session

    async def request(self, method: str, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
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
                kwargs["proxy"] = lease.proxy.url
                start = time.perf_counter()
                response = await self.session.request(method, url, **kwargs)
                latency_ms = (time.perf_counter() - start) * 1000

                if response.status in self.retry_http_codes:
                    if attempt < self.max_retries:
                        tried.add(lease.proxy.key)
                        self.pool.report_failure(lease.proxy)
                        response.release()
                        continue
                    self.pool.report_failure(lease.proxy)
                    return response

                if 200 <= response.status < 400:
                    self.pool.report_success(lease.proxy, latency_ms)
                else:
                    self.pool.report_failure(lease.proxy)
                return response

            except Exception as exc:
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

    async def get(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        return await self.request("POST", url, **kwargs)
