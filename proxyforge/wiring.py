"""组件装配：根据配置与存储后端创建分布式协调器与限流器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from proxyforge.config import ProxyForgeConfig
from proxyforge.rate_limit import ProxyRateLimiter, RateLimiter

if TYPE_CHECKING:
    from proxyforge.storage.base import BaseStorage
    from proxyforge.storage.redis import RedisStorage
    from proxyforge.storage.redis_coordinator import RedisLeaseCoordinator


def build_distributed_coordinator(
    config: ProxyForgeConfig,
    storage: BaseStorage | None,
) -> RedisLeaseCoordinator | None:
    if not config.distributed_enabled or storage is None:
        return None
    from proxyforge.storage.redis import RedisStorage
    from proxyforge.storage.redis_coordinator import RedisLeaseCoordinator

    if not isinstance(storage, RedisStorage):
        return None
    return RedisLeaseCoordinator(
        storage,
        ttl_seconds=config.lease_ttl_seconds,
        max_per_proxy=config.max_leases_per_proxy,
        instance_id=config.instance_id,
    )


def build_rate_limiter(
    config: ProxyForgeConfig,
    storage: BaseStorage | None,
) -> RateLimiter | None:
    if not config.rate_limit_enabled:
        return None
    if config.distributed_enabled and storage is not None:
        from proxyforge.storage.redis import RedisStorage
        from proxyforge.storage.redis_rate_limit import RedisRateLimiter

        if isinstance(storage, RedisStorage):
            return RedisRateLimiter(
                storage,
                max_qps=config.max_qps_per_proxy,
                max_concurrent=config.max_concurrent_per_proxy,
                concurrent_ttl_seconds=max(60, int(config.lease_ttl_seconds * 2)),
            )
    return ProxyRateLimiter(
        max_qps=config.max_qps_per_proxy,
        max_concurrent=config.max_concurrent_per_proxy,
    )
