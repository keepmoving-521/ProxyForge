"""aiohttp 客户端集成。"""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any

from proxyforge.models import Proxy
from proxyforge.pool import ProxyPool

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover - optional dependency
    aiohttp = None  # type: ignore[assignment]


class ProxyForgeClient:
    """aiohttp 封装：自动注入代理并上报使用结果。"""

    def __init__(
        self,
        pool: ProxyPool,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
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
        proxy_obj = self.pool.acquire(strategy=self.strategy, tags=self.tags)
        kwargs.setdefault("proxy", proxy_obj.url)
        start = time.perf_counter()
        try:
            response = await self.session.request(method, url, **kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            if 200 <= response.status < 400:
                self.pool.report_success(proxy_obj, latency_ms)
            else:
                self.pool.report_failure(proxy_obj)
            return response
        except Exception:
            self.pool.report_failure(proxy_obj)
            raise

    async def get(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        return await self.request("POST", url, **kwargs)
