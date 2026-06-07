"""ProxyForge 配置。"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProxyForgeConfig:
    """框架全局配置。"""

    health_check_url: str = "http://httpbin.org/ip"
    health_check_timeout: float = 10.0
    health_check_interval: float = 60.0
    min_score: float = 20.0
    max_consecutive_failures: int = 3
    score_decay_per_failure: float = 10.0
    score_boost_per_success: float = 5.0
    latency_weight: float = 0.3
    success_rate_weight: float = 0.7
    banned_cooldown_seconds: float = 300.0
    user_agent: str = "ProxyForge/0.1.0"
    tags: frozenset[str] = field(default_factory=frozenset)
