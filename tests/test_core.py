"""ProxyForge 单元测试。"""

import pytest

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy, ProxyProtocol, ProxyStatus
from proxyforge.providers.static import StaticListProvider, parse_proxy_lines
from proxyforge.router import ProxyRouter
from proxyforge.scoring import ProxyScorer


def test_proxy_url_without_auth():
    proxy = Proxy(host="1.2.3.4", port=8080)
    assert proxy.url == "http://1.2.3.4:8080"
    assert proxy.key == "http://1.2.3.4:8080"


def test_proxy_url_with_auth():
    proxy = Proxy(
        host="1.2.3.4",
        port=8080,
        username="user",
        password="pass@word",
    )
    assert proxy.url == "http://user:pass%40word@1.2.3.4:8080"


def test_proxy_record_success_and_failure():
    proxy = Proxy(host="1.2.3.4", port=8080)
    proxy.record_success(100.0)
    assert proxy.status == ProxyStatus.HEALTHY
    assert proxy.success_count == 1
    assert proxy.avg_latency_ms == 100.0

    proxy.record_failure()
    proxy.record_failure()
    proxy.record_failure()
    assert proxy.status == ProxyStatus.UNHEALTHY
    assert proxy.consecutive_failures == 3


def test_parse_proxy_lines():
    lines = [
        "1.2.3.4:8080",
        "socks5://5.6.7.8:1080",
        "# comment",
        "http://user:pass@9.10.11.12:3128",
    ]
    proxies = parse_proxy_lines(lines)
    assert len(proxies) == 3
    assert proxies[0].protocol == ProxyProtocol.HTTP
    assert proxies[1].protocol == ProxyProtocol.SOCKS5
    assert proxies[2].username == "user"


@pytest.mark.asyncio
async def test_static_provider():
    provider = StaticListProvider(lines=["10.0.0.1:8888"])
    proxies = await provider.fetch_proxies()
    assert len(proxies) == 1
    assert proxies[0].host == "10.0.0.1"


def test_scorer_compute():
    proxy = Proxy(host="1.2.3.4", port=8080)
    proxy.record_success(200.0)
    proxy.record_success(300.0)
    scorer = ProxyScorer()
    score = scorer.compute(proxy)
    assert 0 <= score <= 100


def test_router_select_best():
    p1 = Proxy(host="1.1.1.1", port=80, score=90.0, status=ProxyStatus.HEALTHY)
    p2 = Proxy(host="2.2.2.2", port=80, score=50.0, status=ProxyStatus.HEALTHY)
    p3 = Proxy(host="3.3.3.3", port=80, score=70.0, status=ProxyStatus.UNHEALTHY)

    router = ProxyRouter(ProxyForgeConfig(min_score=40.0))
    best = router.select_best([p1, p2, p3])
    assert best.host == "1.1.1.1"


def test_router_filter_by_tags():
    p1 = Proxy(
        host="1.1.1.1",
        port=80,
        score=80.0,
        status=ProxyStatus.HEALTHY,
        tags=frozenset({"cn", "mobile"}),
    )
    p2 = Proxy(
        host="2.2.2.2",
        port=80,
        score=80.0,
        status=ProxyStatus.HEALTHY,
        tags=frozenset({"us"}),
    )
    router = ProxyRouter()
    result = router.filter_available([p1, p2], tags=frozenset({"cn"}))
    assert len(result) == 1
    assert result[0].host == "1.1.1.1"
