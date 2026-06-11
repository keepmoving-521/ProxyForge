"""代理状态合并（Provider 元数据 / 运行时统计）。"""

from __future__ import annotations

from proxyforge.models import Proxy


def merge_provider_fields(existing: Proxy, incoming: Proxy) -> None:
    """合并 Provider 拉取的静态字段，保留本地运行时统计。"""
    existing.host = incoming.host
    existing.port = incoming.port
    existing.protocol = incoming.protocol
    existing.username = incoming.username
    existing.password = incoming.password
    existing.provider = incoming.provider
    existing.tags = existing.tags | incoming.tags
    existing.metadata = {**existing.metadata, **incoming.metadata}


def merge_runtime_state(local: Proxy, remote: Proxy) -> None:
    """将持久化存储中的运行时统计合并到本地代理。"""
    local.status = remote.status
    local.score = remote.score
    local.success_count = remote.success_count
    local.failure_count = remote.failure_count
    local.total_latency_ms = remote.total_latency_ms
    local.last_check_at = remote.last_check_at
    local.last_success_at = remote.last_success_at
    local.consecutive_failures = remote.consecutive_failures
    local.banned_at = remote.banned_at
    local.unhealthy_at = remote.unhealthy_at
    local.unhealthy_recheck_attempts = remote.unhealthy_recheck_attempts
    local.recent_events = list(remote.recent_events)
