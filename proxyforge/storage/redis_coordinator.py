"""Redis 分布式租约与状态协调。"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.lease import ProxyLease
from proxyforge.models import Proxy

try:
    from redis.exceptions import ResponseError as RedisResponseError
except ImportError:  # pragma: no cover
    RedisResponseError = Exception

if TYPE_CHECKING:
    from proxyforge.pool import ProxyPool
    from proxyforge.storage.redis import RedisStorage

logger = logging.getLogger(__name__)

_RELEASE_LEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


class RedisLeaseCoordinator:
    """基于 Redis SETNX + TTL 的跨实例租约协调。"""

    def __init__(
        self,
        storage: RedisStorage,
        *,
        ttl_seconds: float = 60.0,
        max_per_proxy: int = 1,
        instance_id: str = "",
    ) -> None:
        self._storage = storage
        self.ttl_seconds = ttl_seconds
        self.max_per_proxy = max_per_proxy
        self.instance_id = instance_id or uuid.uuid4().hex[:12]
        self._release_script = self._storage.sync_client.register_script(
            _RELEASE_LEASE_SCRIPT
        )

    @property
    def sync_client(self):
        return self._storage.sync_client

    def _slot_key(self, proxy_key: str, slot: int) -> str:
        return f"{self._storage.key_prefix}:dlease:{proxy_key}:{slot}"

    def active_lease_count(self, proxy_key: str) -> int:
        client = self.sync_client
        active = 0
        for slot in range(self.max_per_proxy):
            if client.get(self._slot_key(proxy_key, slot)):
                active += 1
        return active

    def is_proxy_leased(self, proxy_key: str) -> bool:
        return self.active_lease_count(proxy_key) >= self.max_per_proxy

    def try_acquire(self, proxy: Proxy) -> ProxyLease | None:
        client = self.sync_client
        lease_id = f"{self.instance_id}:{uuid.uuid4().hex}"
        ttl = max(1, int(self.ttl_seconds))

        for slot in range(self.max_per_proxy):
            key = self._slot_key(proxy.key, slot)
            if client.set(key, lease_id, nx=True, ex=ttl):
                return ProxyLease(
                    lease_id=lease_id,
                    proxy=proxy,
                    created_at=time.time(),
                    ttl_seconds=self.ttl_seconds,
                )
        return None

    def release_lease(self, lease: ProxyLease) -> bool:
        client = self.sync_client
        for slot in range(self.max_per_proxy):
            key = self._slot_key(lease.proxy.key, slot)
            try:
                if self._release_script(keys=[key], args=[lease.lease_id]):
                    return True
            except RedisResponseError:
                if client.get(key) == lease.lease_id:
                    return bool(client.delete(key))
        return False

    def sync_proxy_state(self, local: Proxy) -> bool:
        from proxyforge.pool import ProxyPool

        remote = self._storage.load_proxy_sync(local.key)
        if remote is None:
            return False
        ProxyPool.merge_runtime_state(local, remote)
        return True

    def acquire_lease(
        self,
        pool: ProxyPool,
        *,
        strategy: str = "weighted",
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
        sync_on_acquire: bool = True,
    ) -> ProxyLease:
        local_excluded = pool._lease_manager.get_excluded_keys()
        combined_exclude = local_excluded
        if exclude_keys:
            combined_exclude = local_excluded | exclude_keys

        candidates = pool._router.iter_candidates(
            pool._proxies.values(),
            strategy=strategy,
            tags=tags,
            exclude_keys=combined_exclude,
        )

        for proxy in candidates:
            if self.is_proxy_leased(proxy.key):
                continue
            if sync_on_acquire:
                self.sync_proxy_state(proxy)
            remote_lease = self.try_acquire(proxy)
            if remote_lease is not None:
                return pool._lease_manager.register(remote_lease)

        raise ProxyNotAvailableError("No available proxy matching criteria")
