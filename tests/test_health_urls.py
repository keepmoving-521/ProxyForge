"""健康检测 URL 解析测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from proxyforge.config import ProxyForgeConfig
from proxyforge.health import HealthChecker
from proxyforge.health_urls import HealthCheckContext, HealthCheckUrlResolver
from proxyforge.models import Proxy


def test_resolve_default_url():
    resolver = HealthCheckUrlResolver(ProxyForgeConfig())
    proxy = Proxy(host="1.1.1.1", port=8080)
    assert resolver.resolve(proxy) == "http://httpbin.org/ip"


def test_resolve_by_proxy_tag():
    config = ProxyForgeConfig(
        health_check_urls_by_tag={"cn": "http://cn.example.com/ping"},
    )
    resolver = HealthCheckUrlResolver(config)
    proxy = Proxy(host="1.1.1.1", port=8080, tags=frozenset({"cn"}))
    assert resolver.resolve(proxy) == "http://cn.example.com/ping"


def test_resolve_priority_task_over_tag():
    config = ProxyForgeConfig(
        health_check_urls_by_tag={"cn": "http://cn.example.com/ping"},
        health_check_urls_by_task={"amazon": "https://amazon.com/robots.txt"},
    )
    resolver = HealthCheckUrlResolver(config)
    proxy = Proxy(host="1.1.1.1", port=8080, tags=frozenset({"cn"}))
    ctx = HealthCheckContext(task="amazon")
    assert resolver.resolve(proxy, ctx) == "https://amazon.com/robots.txt"


def test_resolve_spider_url():
    config = ProxyForgeConfig(
        health_check_urls_by_spider={"my_spider": "https://target.com/health"},
    )
    resolver = HealthCheckUrlResolver(config)
    proxy = Proxy(host="1.1.1.1", port=8080)
    ctx = HealthCheckContext(spider="my_spider")
    assert resolver.resolve(proxy, ctx) == "https://target.com/health"


def test_resolve_context_tags_before_proxy_tags():
    config = ProxyForgeConfig(
        health_check_urls_by_tag={
            "cn": "http://cn.example.com/ping",
            "us": "http://us.example.com/ping",
        },
    )
    resolver = HealthCheckUrlResolver(config)
    proxy = Proxy(host="1.1.1.1", port=8080, tags=frozenset({"cn"}))
    ctx = HealthCheckContext(tags=frozenset({"us"}))
    assert resolver.resolve(proxy, ctx) == "http://us.example.com/ping"


def test_resolve_proxy_metadata_override():
    config = ProxyForgeConfig(health_check_url="http://default.example.com")
    resolver = HealthCheckUrlResolver(config)
    proxy = Proxy(host="1.1.1.1", port=8080, metadata={"health_check_url": "http://custom.example.com"})
    assert resolver.resolve(proxy) == "http://custom.example.com"


@pytest.mark.asyncio
async def test_check_one_uses_resolved_url():
    config = ProxyForgeConfig(
        health_check_urls_by_tag={"cn": "http://cn.example.com/ping"},
    )
    checker = HealthChecker(config)
    proxy = Proxy(host="1.1.1.1", port=8080, tags=frozenset({"cn"}))

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    ok = await checker.check_one(proxy, mock_client)
    assert ok is True
    mock_client.get.assert_awaited_once()
    assert mock_client.get.await_args.args[0] == "http://cn.example.com/ping"


def test_pool_resolve_health_check_url():
    from proxyforge.pool import ProxyPool

    config = ProxyForgeConfig(
        health_check_urls_by_spider={"news_spider": "https://news.example.com/robots.txt"},
    )
    pool = ProxyPool(config)
    proxy = Proxy(host="1.1.1.1", port=8080)
    url = pool.resolve_health_check_url(proxy, spider="news_spider")
    assert url == "https://news.example.com/robots.txt"
