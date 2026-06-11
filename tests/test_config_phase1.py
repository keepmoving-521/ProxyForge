"""Phase 1 配置落地测试。"""

from unittest.mock import AsyncMock

import pytest

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool
from proxyforge.serialization import proxy_from_dict, proxy_to_dict


def test_record_failure_uses_ban_threshold():
    proxy = Proxy(host="1.2.3.4", port=8080)
    proxy.record_success(100.0)
    for _ in range(4):
        proxy.record_failure(max_consecutive_failures=5)
    assert proxy.status == ProxyStatus.UNHEALTHY
    proxy.record_failure(max_consecutive_failures=5)
    assert proxy.status == ProxyStatus.BANNED
    assert proxy.banned_at is not None


def test_banned_cooldown_recovery():
    proxy = Proxy(
        host="1.1.1.1",
        port=80,
        status=ProxyStatus.BANNED,
        banned_at=1000.0,
    )
    assert not proxy.is_available(banned_cooldown_seconds=300.0, now=1200.0)
    assert proxy.is_available(banned_cooldown_seconds=300.0, now=1301.0)
    assert proxy.status == ProxyStatus.UNKNOWN


def test_allow_unknown_proxies_config():
    proxy = Proxy(host="1.1.1.1", port=80, status=ProxyStatus.UNKNOWN)
    assert proxy.is_available(allow_unknown=True)
    assert not proxy.is_available(allow_unknown=False)


def test_config_from_dict():
    config = ProxyForgeConfig.from_dict(
        {
            "health_check_url": "http://example.com/ip",
            "max_consecutive_failures": 5,
            "banned_cooldown_seconds": 600.0,
            "allow_unknown_proxies": False,
            "tags": ["cn", "mobile"],
        }
    )
    assert config.health_check_url == "http://example.com/ip"
    assert config.max_consecutive_failures == 5
    assert config.banned_cooldown_seconds == 600.0
    assert config.allow_unknown_proxies is False
    assert config.tags == frozenset({"cn", "mobile"})


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("PROXYFORGE_HEALTH_CHECK_URL", "http://test.local/ip")
    monkeypatch.setenv("PROXYFORGE_MAX_CONSECUTIVE_FAILURES", "7")
    monkeypatch.setenv("PROXYFORGE_BANNED_COOLDOWN_SECONDS", "120")
    monkeypatch.setenv("PROXYFORGE_ALLOW_UNKNOWN_PROXIES", "false")
    monkeypatch.setenv("PROXYFORGE_TAGS", "cn, mobile")

    config = ProxyForgeConfig.from_env()
    assert config.health_check_url == "http://test.local/ip"
    assert config.max_consecutive_failures == 7
    assert config.banned_cooldown_seconds == 120.0
    assert config.allow_unknown_proxies is False
    assert config.tags == frozenset({"cn", "mobile"})


def test_config_to_dict_roundtrip():
    original = ProxyForgeConfig(
        max_consecutive_failures=4,
        allow_unknown_proxies=False,
        tags=frozenset({"us"}),
    )
    restored = ProxyForgeConfig.from_dict(original.to_dict())
    assert restored == original


def test_config_from_yaml(tmp_path):
    yaml = pytest.importorskip("yaml")
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "health_check_url": "http://yaml.local/ip",
                "max_consecutive_failures": 2,
            }
        ),
        encoding="utf-8",
    )
    config = ProxyForgeConfig.from_yaml(path)
    assert config.health_check_url == "http://yaml.local/ip"
    assert config.max_consecutive_failures == 2


def test_merge_preserves_runtime_stats():
    pool = ProxyPool()
    existing = Proxy(
        host="1.1.1.1",
        port=8080,
        score=95.0,
        status=ProxyStatus.HEALTHY,
        success_count=10,
    )
    pool.add_proxy(existing)

    incoming = Proxy(host="1.1.1.1", port=8080, provider="vendor_b", score=10.0)
    pool.add_proxy(incoming)

    merged = pool.get(existing.key)
    assert merged is not None
    assert merged.score == 95.0
    assert merged.success_count == 10
    assert merged.provider == "vendor_b"


def test_banned_at_serialization():
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        status=ProxyStatus.BANNED,
        banned_at=1234567890.0,
    )
    restored = proxy_from_dict(proxy_to_dict(proxy))
    assert restored.banned_at == proxy.banned_at
    assert restored.status == ProxyStatus.BANNED


@pytest.mark.asyncio
async def test_report_failure_schedules_persist():
    storage = AsyncMock()
    pool = ProxyPool(
        ProxyForgeConfig(max_consecutive_failures=2),
        storage=storage,
        auto_persist=True,
    )
    proxy = Proxy(host="1.1.1.1", port=8080, score=80.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)

    pool.report_failure(proxy)
    await asyncio_pending_tasks()

    storage.save_proxy.assert_awaited()


async def asyncio_pending_tasks():
    import asyncio

    await asyncio.sleep(0)


def test_router_respects_allow_unknown():
    from proxyforge.router import ProxyRouter

    config = ProxyForgeConfig(min_score=10.0, allow_unknown_proxies=False)
    router = ProxyRouter(config)
    unknown = Proxy(host="1.1.1.1", port=80, score=80.0, status=ProxyStatus.UNKNOWN)
    healthy = Proxy(host="2.2.2.2", port=80, score=80.0, status=ProxyStatus.HEALTHY)

    assert router.filter_available([unknown, healthy]) == [healthy]
