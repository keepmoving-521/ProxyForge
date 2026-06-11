"""滑动窗口评分测试。"""

import time

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy
from proxyforge.services import ProxyScorer
from proxyforge.services.score_window import append_score_event, window_stats


def test_window_stats_ignores_old_events():
    proxy = Proxy(host="1.1.1.1", port=8080)
    now = 1000.0
    proxy.recent_events = [
        (now - 7200, True, 100.0),
        (now - 100, True, 200.0),
        (now - 50, False, 0.0),
    ]
    stats = window_stats(
        proxy,
        window_seconds=3600.0,
        max_events=500,
        now=now,
    )
    assert stats is not None
    assert stats.sample_count == 2
    assert stats.success_rate == 0.5
    assert stats.avg_latency_ms == 200.0


def test_scorer_prefers_recent_failures_over_lifetime_success():
    config = ProxyForgeConfig(
        score_window_enabled=True,
        score_window_seconds=3600.0,
        success_rate_weight=1.0,
        latency_weight=0.0,
    )
    scorer = ProxyScorer(config)
    proxy = Proxy(host="1.1.1.1", port=8080, score=90.0)
    proxy.success_count = 100
    proxy.failure_count = 0

    now = time.time()
    proxy.recent_events = [
        (now - 10, False, 0.0),
        (now - 5, False, 0.0),
    ]

    score = scorer.compute(proxy)
    assert score == 0.0


def test_scorer_falls_back_without_window_events():
    config = ProxyForgeConfig(score_window_enabled=True)
    scorer = ProxyScorer(config)
    proxy = Proxy(host="1.1.1.1", port=8080, score=77.0)
    assert scorer.compute(proxy) == 77.0


def test_scorer_cumulative_when_window_disabled():
    config = ProxyForgeConfig(score_window_enabled=False, success_rate_weight=1.0, latency_weight=0.0)
    scorer = ProxyScorer(config)
    proxy = Proxy(host="1.1.1.1", port=8080)
    proxy.record_success(100.0)
    proxy.record_failure()
    score = scorer.compute(proxy)
    assert score == 50.0


def test_append_score_event_on_record():
    proxy = Proxy(host="1.1.1.1", port=8080)
    proxy.record_success(120.0)
    proxy.record_failure()
    assert len(proxy.recent_events) == 2
    assert proxy.recent_events[0][1] is True
    assert proxy.recent_events[1][1] is False
