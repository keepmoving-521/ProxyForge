"""Redis 分布式租约与状态同步测试。"""

import pytest

from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.state import merge_runtime_state
from proxyforge.storage.redis_coordinator import RedisLeaseCoordinator
from conftest import make_distributed_pool


def test_distributed_lease_prevents_cross_instance_conflict(shared_storage):
    proxy = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool_a = make_distributed_pool(shared_storage, instance_id="node-a", proxies=[proxy])
    pool_b = make_distributed_pool(shared_storage, instance_id="node-b", proxies=[proxy])

    lease_a = pool_a.acquire_lease(strategy="best")
    assert lease_a.proxy.key == proxy.key

    with pytest.raises(ProxyNotAvailableError):
        pool_b.acquire_lease(strategy="best")

    pool_a.release_lease(lease_a)
    lease_b = pool_b.acquire_lease(strategy="best")
    assert lease_b.proxy.key == proxy.key


def test_distributed_syncs_score_on_acquire(shared_storage):
    proxy = Proxy(host="2.2.2.2", port=8080, score=50.0, status=ProxyStatus.HEALTHY)
    pool_a = make_distributed_pool(
        shared_storage, instance_id="node-a", proxies=[proxy], auto_persist=True
    )
    pool_b = make_distributed_pool(shared_storage, instance_id="node-b", proxies=[proxy])

    remote = pool_a.get(proxy.key)
    assert remote is not None
    remote.score = 99.0
    pool_a.flush_persist_sync()

    lease = pool_b.acquire_lease(strategy="best")
    assert lease.proxy.score == 99.0


def test_redis_coordinator_try_acquire_and_release(shared_storage):
    proxy = Proxy(host="3.3.3.3", port=8080, score=80.0, status=ProxyStatus.HEALTHY)
    coordinator = RedisLeaseCoordinator(
        shared_storage,
        ttl_seconds=60.0,
        max_per_proxy=1,
        instance_id="coord-test",
    )

    lease = coordinator.try_acquire(proxy)
    assert lease is not None
    assert coordinator.is_proxy_leased(proxy.key)
    assert coordinator.try_acquire(proxy) is None

    assert coordinator.release_lease(lease)
    assert not coordinator.is_proxy_leased(proxy.key)


def test_merge_runtime_state_copies_stats():
    local = Proxy(host="4.4.4.4", port=8080, score=10.0, status=ProxyStatus.UNKNOWN)
    remote = Proxy(
        host="4.4.4.4",
        port=8080,
        score=88.0,
        status=ProxyStatus.HEALTHY,
        success_count=5,
        failure_count=2,
        consecutive_failures=0,
    )

    merge_runtime_state(local, remote)

    assert local.score == 88.0
    assert local.status == ProxyStatus.HEALTHY
    assert local.success_count == 5
    assert local.failure_count == 2
