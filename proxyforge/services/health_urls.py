"""健康检测 URL 解析。"""

from __future__ import annotations

from dataclasses import dataclass

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy


@dataclass(frozen=True, slots=True)
class HealthCheckContext:
    """健康检测上下文，用于按任务 / spider / 标签选择 URL。"""

    task: str | None = None
    spider: str | None = None
    tags: frozenset[str] | None = None


class HealthCheckUrlResolver:
    """按优先级解析健康检测 URL。"""

    def __init__(self, config: ProxyForgeConfig) -> None:
        self.config = config

    def resolve(
        self,
        proxy: Proxy,
        context: HealthCheckContext | None = None,
    ) -> str:
        ctx = context or HealthCheckContext()

        if ctx.task:
            url = self.config.health_check_urls_by_task.get(ctx.task)
            if url:
                return url

        if ctx.spider:
            url = self.config.health_check_urls_by_spider.get(ctx.spider)
            if url:
                return url

        if ctx.tags:
            for tag in sorted(ctx.tags):
                url = self.config.health_check_urls_by_tag.get(tag)
                if url:
                    return url

        for tag in sorted(proxy.tags):
            url = self.config.health_check_urls_by_tag.get(tag)
            if url:
                return url

        meta_url = proxy.metadata.get("health_check_url")
        if isinstance(meta_url, str) and meta_url.strip():
            return meta_url.strip()

        return self.config.health_check_url
