"""Redis 分布式限流测试。"""

import time

import pytest

from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.rate_limit import ProxyRateLimiter
from proxyforge.services.storage.redis_rate_limit import RedisRateLimiter
from conftest import make_distributed_pool, make_pool


def test_redis_rate_limiter_concurrent(shared_storage):
    limiter = RedisRateLimiter(shared_storage, max_qps=0.0, max_concurrent=2)
    key = "http://1.1.1.1:8080"

    assert limiter.try_acquire(key)
    assert limiter.try_acquire(key)
    assert not limiter.try_acquire(key)

    limiter.release(key)
    assert limiter.try_acquire(key)


def test_redis_rate_limiter_qps_window(shared_storage):
    limiter = RedisRateLimiter(shared_storage, max_qps=2.0, max_concurrent=0)
    key = "http://2.2.2.2:8080"

    assert limiter.try_acquire(key)
    assert limiter.try_acquire(key)
    assert not limiter.try_acquire(key)

    time.sleep(1.05)
    assert limiter.try_acquire(key)


def test_distributed_concurrent_limit_across_instances(shared_storage):
    proxy = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool_a = make_distributed_pool(
        shared_storage,
        instance_id="node-a",
        proxies=[proxy],
        rate_limit_enabled=True,
        max_concurrent_per_proxy=1,
    )
    pool_b = make_distributed_pool(
        shared_storage,
        instance_id="node-b",
        proxies=[proxy],
        rate_limit_enabled=True,
        max_concurrent_per_proxy=1,
    )
    assert isinstance(pool_a.rate_limiter, RedisRateLimiter)

    lease_a = pool_a.acquire_lease(strategy="best")
    assert lease_a.rate_slot_held

    with pytest.raises(ProxyNotAvailableError):
        pool_b.acquire_lease(strategy="best")

    pool_a.release_lease(lease_a)
    lease_b = pool_b.acquire_lease(strategy="best")
    assert lease_b.proxy.key == proxy.key


def test_distributed_qps_limit_across_instances(shared_storage):
    proxy = Proxy(host="3.3.3.3", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool_a = make_distributed_pool(
        shared_storage,
        instance_id="node-a",
        proxies=[proxy],
        rate_limit_enabled=True,
        max_qps_per_proxy=1.0,
        max_concurrent_per_proxy=10,
    )
    pool_b = make_distributed_pool(
        shared_storage,
        instance_id="node-b",
        proxies=[proxy],
        rate_limit_enabled=True,
        max_qps_per_proxy=1.0,
        max_concurrent_per_proxy=10,
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
    pool = make_pool(
        Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY),
        lease_enabled=True,
        distributed_enabled=False,
        rate_limit_enabled=True,
        max_concurrent_per_proxy=1,
    )
    assert isinstance(pool.rate_limiter, ProxyRateLimiter)
