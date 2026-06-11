"""代理动态评分。"""

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy
from proxyforge.score_window import window_stats


class ProxyScorer:
    """基于成功率与延迟计算代理综合得分。"""

    def __init__(self, config: ProxyForgeConfig | None = None) -> None:
        self.config = config or ProxyForgeConfig()

    def _resolve_metrics(self, proxy: Proxy) -> tuple[float, float] | None:
        if self.config.score_window_enabled:
            stats = window_stats(
                proxy,
                window_seconds=self.config.score_window_seconds,
                max_events=self.config.score_window_max_events,
            )
            if stats is None:
                return None
            return stats.success_rate, stats.avg_latency_ms

        total = proxy.success_count + proxy.failure_count
        if total == 0:
            return None
        return proxy.success_rate, proxy.avg_latency_ms

    def compute(self, proxy: Proxy) -> float:
        metrics = self._resolve_metrics(proxy)
        if metrics is None:
            return proxy.score

        success_rate, avg_latency = metrics
        success_component = success_rate * 100.0
        if avg_latency == float("inf"):
            latency_component = 0.0
        else:
            latency_component = max(0.0, 100.0 - avg_latency / 5.0)

        raw = (
            success_component * self.config.success_rate_weight
            + latency_component * self.config.latency_weight
        )
        return max(0.0, min(100.0, raw))

    def update_after_check(self, proxy: Proxy, success: bool) -> None:
        if success:
            proxy.score = min(
                100.0,
                proxy.score + self.config.score_boost_per_success,
            )
        else:
            proxy.score = max(
                0.0,
                proxy.score - self.config.score_decay_per_failure,
            )
        proxy.score = self.compute(proxy)
