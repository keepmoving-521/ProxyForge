"""代理租约管理。"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass

from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.models import Proxy


@dataclass(slots=True)
class ProxyLease:
    """代理租约，持有期间代理不会被再次分配。"""

    lease_id: str
    proxy: Proxy
    created_at: float
    ttl_seconds: float

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at >= self.ttl_seconds

    @property
    def remaining_seconds(self) -> float:
        elapsed = time.time() - self.created_at
        return max(0.0, self.ttl_seconds - elapsed)


class LeaseManager:
    """线程安全的代理租约管理器。"""

    def __init__(
        self,
        *,
        ttl_seconds: float = 60.0,
        max_per_proxy: int = 1,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_per_proxy = max_per_proxy
        self._leases: dict[str, ProxyLease] = {}
        self._proxy_lease_ids: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def register(self, lease: ProxyLease) -> ProxyLease:
        """注册已在外部（如 Redis）创建的租约。"""
        with self._lock:
            self._cleanup_expired_locked()
            self._leases[lease.lease_id] = lease
            self._proxy_lease_ids.setdefault(lease.proxy.key, set()).add(
                lease.lease_id
            )
            return lease

    def create(self, proxy: Proxy) -> ProxyLease:
        with self._lock:
            self._cleanup_expired_locked()
            active = self._active_count_locked(proxy.key)
            if active >= self.max_per_proxy:
                raise ProxyNotAvailableError(
                    f"Proxy {proxy.key} has reached max leases ({self.max_per_proxy})"
                )
            lease = ProxyLease(
                lease_id=uuid.uuid4().hex,
                proxy=proxy,
                created_at=time.time(),
                ttl_seconds=self.ttl_seconds,
            )
            self._leases[lease.lease_id] = lease
            self._proxy_lease_ids.setdefault(proxy.key, set()).add(lease.lease_id)
            return lease

    def release(self, lease: ProxyLease | str) -> None:
        lease_id = lease.lease_id if isinstance(lease, ProxyLease) else lease
        with self._lock:
            stored = self._leases.pop(lease_id, None)
            if stored is None:
                return
            ids = self._proxy_lease_ids.get(stored.proxy.key)
            if ids:
                ids.discard(lease_id)
                if not ids:
                    self._proxy_lease_ids.pop(stored.proxy.key, None)

    def get_excluded_keys(self) -> frozenset[str]:
        """已达租约上限、不可再分配的代理 key。"""
        with self._lock:
            self._cleanup_expired_locked()
            excluded: set[str] = set()
            for key, lease_ids in self._proxy_lease_ids.items():
                active = sum(
                    1
                    for lid in lease_ids
                    if lid in self._leases and not self._leases[lid].is_expired
                )
                if active >= self.max_per_proxy:
                    excluded.add(key)
            return frozenset(excluded)

    def active_count(self) -> int:
        with self._lock:
            self._cleanup_expired_locked()
            return len(self._leases)

    def _active_count_locked(self, proxy_key: str) -> int:
        lease_ids = self._proxy_lease_ids.get(proxy_key, set())
        return sum(
            1
            for lid in lease_ids
            if lid in self._leases and not self._leases[lid].is_expired
        )

    def _cleanup_expired_locked(self) -> None:
        expired = [lid for lid, lease in self._leases.items() if lease.is_expired]
        for lease_id in expired:
            stored = self._leases.pop(lease_id)
            ids = self._proxy_lease_ids.get(stored.proxy.key)
            if ids:
                ids.discard(lease_id)
                if not ids:
                    self._proxy_lease_ids.pop(stored.proxy.key, None)

    def cleanup_expired(self) -> None:
        with self._lock:
            self._cleanup_expired_locked()
