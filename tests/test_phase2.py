"""Phase 2 生产加固测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from proxyforge.config import ProxyForgeConfig
from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.integrations.httpx_client import ProxyForgeHttpxClient
from proxyforge.integrations.scrapy import (
    LEASE_META_KEY,
    RETRY_COUNT_KEY,
    TRIED_PROXIES_KEY,
    ProxyForgeMiddleware,
)
from proxyforge.lease import LeaseManager
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool


def _make_pool(*proxies: Proxy) -> ProxyPool:
    config = ProxyForgeConfig(
        lease_enabled=True,
        lease_ttl_seconds=60.0,
        max_leases_per_proxy=1,
        max_proxy_retries=2,
    )
    pool = ProxyPool(config)
    for proxy in proxies:
        pool.add_proxy(proxy)
    return pool


def test_lease_prevents_double_acquire():
    pool = _make_pool(
        Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    )
    lease1 = pool.acquire_lease(strategy="best")
    assert lease1.proxy.host == "1.1.1.1"

    with pytest.raises(ProxyNotAvailableError):
        pool.acquire_lease(strategy="best")

    pool.release_lease(lease1)
    lease2 = pool.acquire_lease(strategy="best")
    assert lease2.proxy.host == "1.1.1.1"


def test_lease_expiry_allows_reacquire():
    manager = LeaseManager(ttl_seconds=0.01, max_per_proxy=1)
    proxy = Proxy(host="1.1.1.1", port=8080)
    lease = manager.create(proxy)
    import time

    time.sleep(0.02)
    manager.cleanup_expired()
    assert manager.get_excluded_keys() == frozenset()
    manager.release(lease)


def test_acquire_excludes_tried_proxies():
    pool = _make_pool(
        Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY),
        Proxy(host="2.2.2.2", port=8080, score=80.0, status=ProxyStatus.HEALTHY),
    )
    lease = pool.acquire_lease(strategy="best", exclude_keys=frozenset({"http://1.1.1.1:8080"}))
    assert lease.proxy.host == "2.2.2.2"
    pool.release_lease(lease)


def test_scrapy_middleware_retry_on_403():
    pool = _make_pool(
        Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY),
        Proxy(host="2.2.2.2", port=8080, score=80.0, status=ProxyStatus.HEALTHY),
    )
    middleware = ProxyForgeMiddleware(
        pool, strategy="best", max_retries=2, retry_http_codes=frozenset({403})
    )

    request = SimpleNamespace(
        url="http://example.com",
        meta={},
        dont_filter=False,
    )
    request.copy = MagicMock(return_value=SimpleNamespace(
        url=request.url,
        meta={},
        dont_filter=False,
    ))

    middleware.process_request(request, spider=None)
    assert request.meta[LEASE_META_KEY].proxy.host == "1.1.1.1"

    response = SimpleNamespace(status=403)
    result = middleware.process_response(request, response, spider=None)

    assert result is request.copy.return_value
    new_meta = request.copy.return_value.meta
    assert new_meta[RETRY_COUNT_KEY] == 1
    assert "http://1.1.1.1:8080" in new_meta[TRIED_PROXIES_KEY]


def test_scrapy_middleware_releases_lease_on_success():
    pool = _make_pool(
        Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY),
    )
    middleware = ProxyForgeMiddleware(pool)
    lease = pool.acquire_lease()
    request = SimpleNamespace(
        url="http://example.com",
        meta={
            "proxyforge_proxy": lease.proxy,
            LEASE_META_KEY: lease,
            "_proxyforge_start": 0.0,
        },
    )
    response = SimpleNamespace(status=200)

    middleware.process_response(request, response, spider=None)
    assert pool.active_leases == 0
    assert lease.proxy.success_count == 1


@pytest.mark.asyncio
async def test_httpx_client_with_retry():
    pool = _make_pool(
        Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY),
        Proxy(host="2.2.2.2", port=8080, score=80.0, status=ProxyStatus.HEALTHY),
    )

    responses = [
        httpx.Response(403, request=httpx.Request("GET", "http://example.com")),
        httpx.Response(200, request=httpx.Request("GET", "http://example.com")),
    ]

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=responses)
    mock_client.aclose = AsyncMock()

    client = ProxyForgeHttpxClient(
        pool,
        max_retries=2,
        retry_http_codes=frozenset({403}),
        client=mock_client,
    )

    async with client:
        response = await client.get("http://example.com")

    assert response.status_code == 200
    assert mock_client.request.await_count == 2
    assert pool.active_leases == 0


def test_stats_includes_active_leases():
    pool = _make_pool(
        Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY),
    )
    pool.acquire_lease()
    stats = pool.stats()
    assert stats["active_leases"] == 1
