"""Proxy 序列化与反序列化。"""

from __future__ import annotations

from typing import Any

from proxyforge.models import Proxy, ProxyProtocol, ProxyStatus


def proxy_to_dict(proxy: Proxy) -> dict[str, Any]:
    return {
        "host": proxy.host,
        "port": proxy.port,
        "protocol": proxy.protocol.value,
        "username": proxy.username,
        "password": proxy.password,
        "provider": proxy.provider,
        "tags": sorted(proxy.tags),
        "status": proxy.status.value,
        "score": proxy.score,
        "success_count": proxy.success_count,
        "failure_count": proxy.failure_count,
        "total_latency_ms": proxy.total_latency_ms,
        "last_check_at": proxy.last_check_at,
        "last_success_at": proxy.last_success_at,
        "consecutive_failures": proxy.consecutive_failures,
        "banned_at": proxy.banned_at,
        "unhealthy_at": proxy.unhealthy_at,
        "unhealthy_recheck_attempts": proxy.unhealthy_recheck_attempts,
        "metadata": proxy.metadata,
    }


def proxy_from_dict(data: dict[str, Any]) -> Proxy:
    tags = data.get("tags") or []
    return Proxy(
        host=data["host"],
        port=int(data["port"]),
        protocol=ProxyProtocol(data.get("protocol", "http")),
        username=data.get("username"),
        password=data.get("password"),
        provider=data.get("provider", "manual"),
        tags=frozenset(tags),
        status=ProxyStatus(data.get("status", "unknown")),
        score=float(data.get("score", 50.0)),
        success_count=int(data.get("success_count", 0)),
        failure_count=int(data.get("failure_count", 0)),
        total_latency_ms=float(data.get("total_latency_ms", 0.0)),
        last_check_at=data.get("last_check_at"),
        last_success_at=data.get("last_success_at"),
        consecutive_failures=int(data.get("consecutive_failures", 0)),
        banned_at=data.get("banned_at"),
        unhealthy_at=data.get("unhealthy_at"),
        unhealthy_recheck_attempts=int(data.get("unhealthy_recheck_attempts", 0)),
        metadata=dict(data.get("metadata") or {}),
    )
