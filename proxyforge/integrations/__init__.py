"""框架集成：Scrapy / aiohttp / httpx。"""

from proxyforge.integrations.aiohttp import ProxyForgeClient
from proxyforge.integrations.httpx_client import ProxyForgeHttpxClient
from proxyforge.integrations.scrapy import ProxyForgeMiddleware

__all__ = ["ProxyForgeClient", "ProxyForgeHttpxClient", "ProxyForgeMiddleware"]
