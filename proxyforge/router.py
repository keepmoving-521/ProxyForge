"""代理智能路由与调度。"""

from __future__ import annotations

import random
from typing import Iterable

from proxyforge.config import ProxyForgeConfig
from proxyforge.exceptions import ProxyNotAvailableError
from proxyforge.models import Proxy


class ProxyRouter:
    """根据评分与标签筛选并调度代理。"""

    def __init__(self, config: ProxyForgeConfig | None = None) -> None:
        self.config = config or ProxyForgeConfig()

    def filter_available(
        self,
        proxies: Iterable[Proxy],
        *,
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
    ) -> list[Proxy]:
        required_tags = tags or self.config.tags
        excluded = exclude_keys or frozenset()
        candidates: list[Proxy] = []
        for proxy in proxies:
            if proxy.key in excluded:
                continue
            if not proxy.is_available(
                banned_cooldown_seconds=self.config.banned_cooldown_seconds,
                allow_unknown=self.config.allow_unknown_proxies,
            ):
                continue
            if proxy.score < self.config.min_score:
                continue
            if required_tags and not required_tags.issubset(proxy.tags):
                continue
            candidates.append(proxy)
        return candidates

    def select_best(
        self,
        proxies: Iterable[Proxy],
        *,
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
    ) -> Proxy:
        candidates = self.filter_available(proxies, tags=tags, exclude_keys=exclude_keys)
        if not candidates:
            raise ProxyNotAvailableError("No available proxy matching criteria")
        return max(candidates, key=lambda p: p.score)

    def select_weighted_random(
        self,
        proxies: Iterable[Proxy],
        *,
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
    ) -> Proxy:
        candidates = self.filter_available(proxies, tags=tags, exclude_keys=exclude_keys)
        if not candidates:
            raise ProxyNotAvailableError("No available proxy matching criteria")
        weights = [max(p.score, 1.0) for p in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    def select_round_robin(
        self,
        proxies: Iterable[Proxy],
        *,
        tags: frozenset[str] | None = None,
        exclude_keys: frozenset[str] | None = None,
    ) -> Proxy:
        candidates = self.filter_available(proxies, tags=tags, exclude_keys=exclude_keys)
        if not candidates:
            raise ProxyNotAvailableError("No available proxy matching criteria")
        candidates.sort(key=lambda p: p.key)
        if not hasattr(self, "_rr_index"):
            self._rr_index = 0
        proxy = candidates[self._rr_index % len(candidates)]
        self._rr_index += 1
        return proxy
