"""框架集成：Scrapy / aiohttp。"""

from proxyforge.integrations.aiohttp import ProxyForgeClient
from proxyforge.integrations.scrapy import ProxyForgeMiddleware

__all__ = ["ProxyForgeClient", "ProxyForgeMiddleware"]
