"""代理动态评分。"""

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy


class ProxyScorer:
    """基于成功率与延迟计算代理综合得分。"""

    def __init__(self, config: ProxyForgeConfig | None = None) -> None:
        self.config = config or ProxyForgeConfig()

    def compute(self, proxy: Proxy) -> float:
        total = proxy.success_count + proxy.failure_count
        if total == 0:
            return proxy.score

        success_component = proxy.success_rate * 100.0
        latency = proxy.avg_latency_ms
        if latency == float("inf"):
            latency_component = 0.0
        else:
            # 延迟越低得分越高，500ms 以上趋近于 0
            latency_component = max(0.0, 100.0 - latency / 5.0)

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
