"""序列化测试。"""

from proxyforge.models import Proxy, ProxyProtocol, ProxyStatus
from proxyforge.serialization import proxy_from_dict, proxy_to_dict


def test_proxy_roundtrip():
    proxy = Proxy(
        host="1.2.3.4",
        port=8080,
        protocol=ProxyProtocol.HTTP,
        username="user",
        password="pass",
        provider="test",
        tags=frozenset({"cn"}),
        status=ProxyStatus.HEALTHY,
        score=88.5,
        success_count=10,
        failure_count=2,
        total_latency_ms=1500.0,
        consecutive_failures=0,
        metadata={"region": "beijing"},
    )
    restored = proxy_from_dict(proxy_to_dict(proxy))
    assert restored.key == proxy.key
    assert restored.score == proxy.score
    assert restored.tags == proxy.tags
    assert restored.metadata == proxy.metadata
