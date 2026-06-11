"""租约获取编排：统一本地与分布式 acquire 流程。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from proxyforge.config import ProxyForgeConfig
from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.lease import LeaseManager, ProxyLease
from proxyforge.models import Proxy
from proxyforge.rate_limit import RateLimiter
from proxyforge.router import ProxyRouter

if TYPE_CHECKING:
    from proxyforge.storage.redis_coordinator import RedisLeaseCoordinator


class LeaseAcquisitionService:
    """候选筛选、租约创建、限流与分布式协调的统一入口。"""

    def __init__(
        self,
        *,
        config: ProxyForgeConfig,
        lease_manager: LeaseManager,
        router: ProxyRouter,
        get_proxies: Callable[[], Iterable[Proxy]],
        rate_limiter: RateLimiter | None = None,
        distributed: RedisLeaseCoordinator | None = None,
    ) -> None:
        self._config = config
        self._lease_manager = lease_manager
        self._router = router
        self._get_proxies = get_proxies
        self._rate_limiter = rate_limiter
        self._distributed = distributed

    def acquire(
        self,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
        sync_on_acquire: bool = True,
    ) -> ProxyLease:
        for proxy in self.iter_candidates(
            strategy=strategy, tags=tags, exclude_keys=exclude_keys
        ):
            if self.is_proxy_blocked(proxy.key):
                continue
            lease = self.try_create_lease(proxy, sync_on_acquire=sync_on_acquire)
            if lease is None:
                continue
            lease = self.apply_rate_limit_or_abort(lease)
            if lease is not None:
                return lease
        raise ProxyNotAvailableError("No available proxy matching criteria")

    def iter_candidates(
        self,
        *,
        strategy: str,
        tags: frozenset[str] | None,
        exclude_keys: frozenset[str] | None,
    ) -> list[Proxy]:
        leased = self._lease_manager.get_excluded_keys()
        combined_exclude = leased
        if exclude_keys:
            combined_exclude = leased | exclude_keys
        return self._router.iter_candidates(
            self._get_proxies(),
            strategy=strategy,
            tags=tags,
            exclude_keys=combined_exclude,
        )

    def is_proxy_blocked(self, proxy_key: str) -> bool:
        if self._distributed is not None and self._distributed.is_proxy_leased(
            proxy_key
        ):
            return True
        if (
            self._rate_limiter is not None
            and self._rate_limiter.is_at_capacity(proxy_key)
        ):
            return True
        return False

    def try_create_lease(
        self, proxy: Proxy, *, sync_on_acquire: bool = True
    ) -> ProxyLease | None:
        if self._distributed is not None and self._config.lease_enabled:
            if sync_on_acquire:
                self._distributed.sync_proxy_state(proxy)
            remote = self._distributed.try_acquire(proxy)
            if remote is None:
                return None
            return self._lease_manager.register(remote)
        try:
            return self._create_local_lease(proxy)
        except ProxyNotAvailableError:
            return None

    def apply_rate_limit_or_abort(self, lease: ProxyLease) -> ProxyLease | None:
        if self._rate_limiter is None:
            return lease
        if self._rate_limiter.try_acquire(lease.proxy.key):
            lease.rate_slot_held = True
            return lease
        self.abort_lease(lease)
        return None

    def abort_lease(self, lease: ProxyLease) -> None:
        if lease.rate_slot_held and self._rate_limiter is not None:
            self._rate_limiter.release(lease.proxy.key)
            lease.rate_slot_held = False
        if lease.lease_id:
            self._lease_manager.release(lease)
            if self._distributed is not None:
                self._distributed.release_lease(lease)

    def release_rate_slot(self, lease: ProxyLease) -> None:
        if lease.rate_slot_held and self._rate_limiter is not None:
            self._rate_limiter.release(lease.proxy.key)
            lease.rate_slot_held = False

    def _create_local_lease(self, proxy: Proxy) -> ProxyLease:
        if self._config.lease_enabled:
            return self._lease_manager.create(proxy)
        return ProxyLease(
            lease_id="",
            proxy=proxy,
            created_at=0.0,
            ttl_seconds=0.0,
        )
