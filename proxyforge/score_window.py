"""兼容导出：请使用 proxyforge.services.score_window。"""

from proxyforge.services.score_window import (
    WindowStats,
    append_score_event,
    prune_score_events,
    window_stats,
)

__all__ = [
    "WindowStats",
    "append_score_event",
    "prune_score_events",
    "window_stats",
]
