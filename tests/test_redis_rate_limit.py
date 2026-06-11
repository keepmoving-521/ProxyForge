"""Redis 分布式限流测试。"""

import time

import pytest

fakeredis = pytest.importorskip("fakeredis")

from proxyforge.config import ProxyForgeConfig
from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool
from proxyforge.storage.redis import RedisStorage
from proxyforge.storage.redis_rate_limit import RedisRateLimiter


@pytest.fixture
def shared_storage():
    server = fakeredis.FakeServer()
    async_client = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    sync_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    store = RedisStorage(
        client=async_client,
        sync_client=sync_client,
        key_prefix="rlimit",
    )
    yield store


def _make_pool(
    storage: RedisStorage,
    *,
    instance_id: str,
    proxies: list[Proxy],
    max_qps: float = 0.0,
    max_concurrent: int = 0,
) -> ProxyPool:
    config = ProxyForgeConfig(
        lease_enabled=True,
        distributed_enabled=True,
        rate_limit_enabled=True,
        max_qps_per_proxy=max_qps,
        max_concurrent_per_proxy=max_concurrent,
        instance_id=instance_id,
        min_score=0.0,
    )
    pool = ProxyPool(config=config, storage=storage)
    for proxy in proxies:
        pool.add_proxy(proxy)
    return pool


def test_redis_rate_limiter_concurrent(shared_storage):
    limiter = RedisRateLimiter(
        shared_storage, max_qps=0.0, max_concurrent=2
    )
    key = "http://1.1.1.1:8080"

    assert limiter.try_acquire(key)
    assert limiter.try_acquire(key)
    assert not limiter.try_acquire(key)

    limiter.release(key)
    assert limiter.try_acquire(key)


def test_redis_rate_limiter_qps_window(shared_storage):
    limiter = RedisRateLimiter(
        shared_storage, max_qps=2.0, max_concurrent=0
    )
    key = "http://2.2.2.2:8080"

    assert limiter.try_acquire(key)
    assert limiter.try_acquire(key)
    assert not limiter.try_acquire(key)

    time.sleep(1.05)
    assert limiter.try_acquire(key)


def test_distributed_concurrent_limit_across_instances(shared_storage):
    proxy = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool_a = _make_pool(
        shared_storage,
        instance_id="node-a",
        proxies=[proxy],
        max_concurrent=1,
    )
    pool_b = _make_pool(
        shared_storage,
        instance_id="node-b",
        proxies=[proxy],
        max_concurrent=1,
    )
    assert isinstance(pool_a._rate_limiter, RedisRateLimiter)

    lease_a = pool_a.acquire_lease(strategy="best")
    assert lease_a.rate_slot_held

    with pytest.raises(ProxyNotAvailableError):
        pool_b.acquire_lease(strategy="best")

    pool_a.release_lease(lease_a)
    lease_b = pool_b.acquire_lease(strategy="best")
    assert lease_b.proxy.key == proxy.key


def test_distributed_qps_limit_across_instances(shared_storage):
    proxy = Proxy(host="3.3.3.3", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool_a = _make_pool(
        shared_storage,
        instance_id="node-a",
        proxies=[proxy],
        max_qps=1.0,
        max_concurrent=10,
    )
    pool_b = _make_pool(
        shared_storage,
        instance_id="node-b",
        proxies=[proxy],
        max_qps=1.0,
        max_concurrent=10,
    )

    lease_a = pool_a.acquire_lease(strategy="best")
    pool_a.release_lease(lease_a)

    with pytest.raises(ProxyNotAvailableError):
        pool_b.acquire_lease(strategy="best")

    time.sleep(1.05)
    lease_b = pool_b.acquire_lease(strategy="best")
    assert lease_b.proxy.key == proxy.key
    pool_b.release_lease(lease_b)


def test_local_limiter_when_not_distributed():
    config = ProxyForgeConfig(
        lease_enabled=True,
        distributed_enabled=False,
        rate_limit_enabled=True,
        max_concurrent_per_proxy=1,
    )
    pool = ProxyPool(config)
    from proxyforge.rate_limit import ProxyRateLimiter

    assert isinstance(pool._rate_limiter, ProxyRateLimiter)
