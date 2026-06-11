"""ProxyForge 配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


def _coerce_value(field_name: str, raw: str) -> Any:
    if field_name == "tags":
        return frozenset(p.strip() for p in raw.split(",") if p.strip())
    if field_name in {"allow_unknown_proxies", "lease_enabled", "score_window_enabled", "persist_sync_fallback"}:
        return raw.lower() in {"1", "true", "yes", "on"}
    if field_name in {
        "max_consecutive_failures",
        "max_leases_per_proxy",
        "max_proxy_retries",
        "health_check_concurrency",
        "health_check_batch_size",
        "score_window_max_events",
        "persist_batch_size",
    }:
        return int(raw)
    if field_name == "retry_http_codes":
        return frozenset(int(code.strip()) for code in raw.split(",") if code.strip())
    if field_name in {
        "health_check_timeout",
        "health_check_interval",
        "unhealthy_check_interval",
        "banned_check_interval",
        "unhealthy_backoff_factor",
        "unhealthy_check_max_interval",
        "score_window_seconds",
        "min_score",
        "score_decay_per_failure",
        "score_boost_per_success",
        "latency_weight",
        "success_rate_weight",
        "banned_cooldown_seconds",
        "lease_ttl_seconds",
    }:
        return float(raw)
    return raw


@dataclass(slots=True)
class ProxyForgeConfig:
    """框架全局配置。"""

    health_check_url: str = "http://httpbin.org/ip"
    health_check_timeout: float = 10.0
    health_check_interval: float = 60.0
    unhealthy_check_interval: float = 300.0
    unhealthy_backoff_factor: float = 2.0
    unhealthy_check_max_interval: float = 3600.0
    banned_check_interval: float = 300.0
    health_check_concurrency: int = 20
    health_check_batch_size: int = 100
    min_score: float = 20.0
    max_consecutive_failures: int = 3
    score_decay_per_failure: float = 10.0
    score_boost_per_success: float = 5.0
    latency_weight: float = 0.3
    success_rate_weight: float = 0.7
    score_window_enabled: bool = True
    score_window_seconds: float = 3600.0
    score_window_max_events: int = 500
    persist_batch_size: int = 10
    persist_sync_fallback: bool = True
    banned_cooldown_seconds: float = 300.0
    allow_unknown_proxies: bool = True
    lease_enabled: bool = True
    lease_ttl_seconds: float = 60.0
    max_leases_per_proxy: int = 1
    max_proxy_retries: int = 3
    retry_http_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({403, 429, 502, 503, 504})
    )
    user_agent: str = "ProxyForge/0.3.0"
    tags: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProxyForgeConfig:
        kwargs: dict[str, Any] = {}
        valid = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key not in valid:
                continue
            if key == "tags" and value is not None:
                kwargs[key] = frozenset(value)
            elif key == "retry_http_codes" and value is not None:
                kwargs[key] = frozenset(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)

    @classmethod
    def from_env(cls, prefix: str = "PROXYFORGE_") -> ProxyForgeConfig:
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            env_key = prefix + f.name.upper()
            raw = os.environ.get(env_key)
            if raw is None:
                continue
            kwargs[f.name] = _coerce_value(f.name, raw)
        return cls(**kwargs)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProxyForgeConfig:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required for from_yaml. Install with: pip install pyyaml"
            ) from exc

        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("YAML config root must be a mapping")
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_check_url": self.health_check_url,
            "health_check_timeout": self.health_check_timeout,
            "health_check_interval": self.health_check_interval,
            "unhealthy_check_interval": self.unhealthy_check_interval,
            "unhealthy_backoff_factor": self.unhealthy_backoff_factor,
            "unhealthy_check_max_interval": self.unhealthy_check_max_interval,
            "banned_check_interval": self.banned_check_interval,
            "health_check_concurrency": self.health_check_concurrency,
            "health_check_batch_size": self.health_check_batch_size,
            "min_score": self.min_score,
            "max_consecutive_failures": self.max_consecutive_failures,
            "score_decay_per_failure": self.score_decay_per_failure,
            "score_boost_per_success": self.score_boost_per_success,
            "latency_weight": self.latency_weight,
            "success_rate_weight": self.success_rate_weight,
            "score_window_enabled": self.score_window_enabled,
            "score_window_seconds": self.score_window_seconds,
            "score_window_max_events": self.score_window_max_events,
            "persist_batch_size": self.persist_batch_size,
            "persist_sync_fallback": self.persist_sync_fallback,
            "banned_cooldown_seconds": self.banned_cooldown_seconds,
            "allow_unknown_proxies": self.allow_unknown_proxies,
            "lease_enabled": self.lease_enabled,
            "lease_ttl_seconds": self.lease_ttl_seconds,
            "max_leases_per_proxy": self.max_leases_per_proxy,
            "max_proxy_retries": self.max_proxy_retries,
            "retry_http_codes": sorted(self.retry_http_codes),
            "user_agent": self.user_agent,
            "tags": sorted(self.tags),
        }
