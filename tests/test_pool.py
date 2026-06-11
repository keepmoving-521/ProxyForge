"""ProxyPool 测试。"""

import pytest

from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool
from proxyforge.services.providers.static import StaticListProvider


@pytest.mark.asyncio
async def test_pool_refresh_and_acquire():
    provider = StaticListProvider(
        lines=["10.0.0.1:8080", "10.0.0.2:8080"],
    )
    pool = ProxyPool(providers=[provider])
    count = await pool.refresh_from_providers()
    assert count == 2
    assert pool.total_count == 2


@pytest.mark.asyncio
async def test_pool_acquire_with_healthy_proxy():
    pool = ProxyPool()
    proxy = Proxy(host="1.2.3.4", port=8080, score=80.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)
    acquired = pool.acquire(strategy="best")
    assert acquired.key == proxy.key


def test_pool_stats():
    pool = ProxyPool()
    pool.add_proxy(Proxy(host="1.1.1.1", port=80, status=ProxyStatus.HEALTHY))
    pool.add_proxy(Proxy(host="2.2.2.2", port=80, status=ProxyStatus.UNHEALTHY))
    stats = pool.stats()
    assert stats["total"] == 2
    assert stats["healthy"] == 1
