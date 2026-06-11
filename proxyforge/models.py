"""代理数据模型。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import quote


class ProxyProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class ProxyStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    BANNED = "banned"


@dataclass(slots=True)
class Proxy:
    """单个代理节点。"""

    host: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: str | None = None
    password: str | None = None
    provider: str = "manual"
    tags: frozenset[str] = field(default_factory=frozenset)

    status: ProxyStatus = ProxyStatus.UNKNOWN
    score: float = 50.0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_check_at: float | None = None
    last_success_at: float | None = None
    consecutive_failures: int = 0
    banned_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        auth = ""
        if self.username and self.password:
            auth = f"{quote(self.username)}:{quote(self.password)}@"
        return f"{self.protocol.value}://{auth}{self.host}:{self.port}"

    @property
    def key(self) -> str:
        return f"{self.protocol.value}://{self.host}:{self.port}"

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def avg_latency_ms(self) -> float:
        if self.success_count == 0:
            return float("inf")
        return self.total_latency_ms / self.success_count

    def record_success(self, latency_ms: float) -> None:
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.consecutive_failures = 0
        self.banned_at = None
        self.status = ProxyStatus.HEALTHY
        now = time.time()
        self.last_check_at = now
        self.last_success_at = now

    def record_failure(self, *, max_consecutive_failures: int = 3) -> None:
        self.failure_count += 1
        self.consecutive_failures += 1
        self.last_check_at = time.time()
        if self.consecutive_failures >= max_consecutive_failures:
            self.status = ProxyStatus.BANNED
            self.banned_at = time.time()
        elif self.status == ProxyStatus.HEALTHY:
            self.status = ProxyStatus.UNHEALTHY

    def recover_from_ban(self) -> None:
        """冷却结束后解除封禁，等待重新检测。"""
        self.status = ProxyStatus.UNKNOWN
        self.banned_at = None
        self.consecutive_failures = 0

    def is_available(
        self,
        *,
        banned_cooldown_seconds: float = 300.0,
        allow_unknown: bool = True,
        now: float | None = None,
    ) -> bool:
        current = now if now is not None else time.time()

        if self.status == ProxyStatus.BANNED:
            if (
                self.banned_at is not None
                and current - self.banned_at >= banned_cooldown_seconds
            ):
                self.recover_from_ban()
                return allow_unknown
            return False

        if self.status == ProxyStatus.UNHEALTHY:
            return False

        if self.status == ProxyStatus.UNKNOWN:
            return allow_unknown

        return True
