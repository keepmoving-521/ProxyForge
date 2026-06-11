"""滑动窗口评分统计。"""

from __future__ import annotations

import time
from dataclasses import dataclass

from proxyforge.models import Proxy


@dataclass(frozen=True, slots=True)
class WindowStats:
    """滑动窗口内的代理表现。"""

    success_rate: float
    avg_latency_ms: float
    sample_count: int


def append_score_event(proxy: Proxy, success: bool, latency_ms: float = 0.0) -> None:
    proxy.recent_events.append(
        (time.time(), success, latency_ms if success else 0.0)
    )


def prune_score_events(
    proxy: Proxy,
    *,
    window_seconds: float,
    max_events: int,
    now: float | None = None,
) -> None:
    current = now if now is not None else time.time()
    cutoff = current - window_seconds
    proxy.recent_events = [
        event for event in proxy.recent_events if event[0] >= cutoff
    ]
    if len(proxy.recent_events) > max_events:
        proxy.recent_events = proxy.recent_events[-max_events:]


def window_stats(
    proxy: Proxy,
    *,
    window_seconds: float,
    max_events: int,
    now: float | None = None,
) -> WindowStats | None:
    prune_score_events(
        proxy,
        window_seconds=window_seconds,
        max_events=max_events,
        now=now,
    )
    if not proxy.recent_events:
        return None

    successes = [event for event in proxy.recent_events if event[1]]
    total = len(proxy.recent_events)
    if not successes:
        return WindowStats(success_rate=0.0, avg_latency_ms=float("inf"), sample_count=total)

    avg_latency = sum(event[2] for event in successes) / len(successes)
    return WindowStats(
        success_rate=len(successes) / total,
        avg_latency_ms=avg_latency,
        sample_count=total,
    )
