"""单 IP 限流测试。"""

import time

import pytest

from proxyforge.config import ProxyForgeConfig
from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool
from proxyforge.rate_limit import ProxyRateLimiter


def _make_pool(
    *proxies: Proxy,
    max_qps: float = 0.0,
    max_concurrent: int = 0,
) -> ProxyPool:
    config = ProxyForgeConfig(
        lease_enabled=True,
        rate_limit_enabled=True,
        max_qps_per_proxy=max_qps,
        max_concurrent_per_proxy=max_concurrent,
        min_score=0.0,
    )
    pool = ProxyPool(config)
    for proxy in proxies:
        pool.add_proxy(proxy)
    return pool


def test_rate_limiter_qps_window():
    limiter = ProxyRateLimiter(max_qps=2.0, max_concurrent=0)

    assert limiter.try_acquire("http://1.1.1.1:8080")
    assert limiter.try_acquire("http://1.1.1.1:8080")
    assert not limiter.try_acquire("http://1.1.1.1:8080")

    time.sleep(1.05)
    assert limiter.try_acquire("http://1.1.1.1:8080")


def test_rate_limiter_concurrent():
    limiter = ProxyRateLimiter(max_qps=0.0, max_concurrent=2)
    key = "http://1.1.1.1:8080"

    assert limiter.try_acquire(key)
    assert limiter.try_acquire(key)
    assert not limiter.try_acquire(key)

    limiter.release(key)
    assert limiter.try_acquire(key)


def test_acquire_lease_respects_concurrent_limit():
    proxy = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool = _make_pool(proxy, max_concurrent=1)

    lease1 = pool.acquire_lease(strategy="best")
    assert lease1.rate_slot_held

    with pytest.raises(ProxyNotAvailableError):
        pool.acquire_lease(strategy="best")

    pool.release_lease(lease1)
    lease2 = pool.acquire_lease(strategy="best")
    assert lease2.proxy.key == proxy.key


def test_acquire_lease_falls_back_when_primary_is_rate_limited():
    p1 = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    p2 = Proxy(host="2.2.2.2", port=8080, score=80.0, status=ProxyStatus.HEALTHY)
    pool = _make_pool(p1, p2, max_concurrent=1)

    lease1 = pool.acquire_lease(strategy="best")
    assert lease1.proxy.key == p1.key

    lease2 = pool.acquire_lease(strategy="best")
    assert lease2.proxy.key == p2.key


def test_acquire_lease_qps_blocks_same_ip():
    proxy = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool = _make_pool(proxy, max_qps=1.0, max_concurrent=10)

    lease1 = pool.acquire_lease(strategy="best")
    pool.release_lease(lease1)

    with pytest.raises(ProxyNotAvailableError):
        pool.acquire_lease(strategy="best")

    time.sleep(1.05)
    lease3 = pool.acquire_lease(strategy="best")
    assert lease3.proxy.key == proxy.key
    pool.release_lease(lease3)


def test_rate_limit_disabled_by_default():
    proxy = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool = ProxyPool(
        ProxyForgeConfig(lease_enabled=False, rate_limit_enabled=False, min_score=0.0)
    )
    pool.add_proxy(proxy)
    assert pool.rate_limiter is None

    for _ in range(5):
        lease = pool.acquire_lease(strategy="best")
        assert not lease.rate_slot_held
