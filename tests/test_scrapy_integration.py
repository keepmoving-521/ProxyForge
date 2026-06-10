"""Scrapy 中间件测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from proxyforge.integrations.scrapy import ProxyForgeMiddleware
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool


def test_scrapy_middleware_assigns_proxy():
    pool = ProxyPool()
    proxy = Proxy(host="1.2.3.4", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)

    middleware = ProxyForgeMiddleware(pool, strategy="best")
    request = SimpleNamespace(url="http://example.com", meta={})

    middleware.process_request(request, spider=None)

    assert request.meta["proxy"] == proxy.url
    assert request.meta["proxyforge_proxy"] is proxy
    assert request.meta["download_slot"] == proxy.key


def test_scrapy_middleware_reports_success_and_failure():
    pool = ProxyPool()
    proxy = Proxy(host="1.2.3.4", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)
    middleware = ProxyForgeMiddleware(pool)

    request = SimpleNamespace(
        url="http://example.com",
        meta={"proxyforge_proxy": proxy, "_proxyforge_start": 0.0},
    )
    response_ok = SimpleNamespace(status=200)
    response_fail = SimpleNamespace(status=503)

    middleware.process_response(request, response_ok, spider=None)
    assert proxy.success_count == 1

    middleware.process_response(request, response_fail, spider=None)
    assert proxy.failure_count == 1


def test_scrapy_middleware_from_crawler():
    pool = ProxyPool()
    crawler = MagicMock()
    crawler.settings.get.side_effect = lambda key, default=None: {
        "PROXYFORGE_POOL": pool,
        "PROXYFORGE_STRATEGY": "round_robin",
        "PROXYFORGE_TAGS": ["cn"],
    }.get(key, default)

    middleware = ProxyForgeMiddleware.from_crawler(crawler)
    assert middleware.pool is pool
    assert middleware.strategy == "round_robin"
    assert middleware.tags == frozenset({"cn"})
