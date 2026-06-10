# Scrapy settings.py 片段示例
#
# PROXYFORGE_POOL = pool  # 在 spider 启动前初始化 ProxyPool 实例
# PROXYFORGE_STRATEGY = "weighted"  # best | weighted | round_robin
# PROXYFORGE_TAGS = ["cn"]
#
# DOWNLOADER_MIDDLEWARES = {
#     "proxyforge.integrations.scrapy.ProxyForgeMiddleware": 350,
# }

"""Scrapy 集成示例（需在 Scrapy 项目中引用）。"""

import asyncio

from proxyforge import ProxyPool
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.providers.static import StaticListProvider


def build_pool() -> ProxyPool:
    provider = StaticListProvider(lines=["127.0.0.1:7890"])
    pool = ProxyPool(providers=[provider])

    async def _init() -> None:
        await pool.refresh_from_providers()
        pool.add_proxy(
            Proxy(host="127.0.0.1", port=7890, score=90.0, status=ProxyStatus.HEALTHY)
        )

    asyncio.run(_init())
    return pool


# 在 Scrapy settings 中:
# PROXYFORGE_POOL = build_pool()
