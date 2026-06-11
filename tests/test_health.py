"""健康检测测试。"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from proxyforge.config import ProxyForgeConfig
from proxyforge.services import HealthChecker
from proxyforge.models import Proxy, ProxyStatus


def test_should_check_always_when_never_checked():
    checker = HealthChecker()
    proxy = Proxy(host="1.1.1.1", port=8080)
    assert checker.should_check(proxy) is True


def test_should_skip_healthy_if_recently_checked():
    config = ProxyForgeConfig(health_check_interval=60.0)
    checker = HealthChecker(config)
    now = time.time()
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        status=ProxyStatus.HEALTHY,
        last_check_at=now - 10.0,
    )
    assert checker.should_check(proxy, now) is False


def test_should_check_unhealthy_after_interval():
    config = ProxyForgeConfig(unhealthy_check_interval=300.0)
    checker = HealthChecker(config)
    now = time.time()
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        status=ProxyStatus.UNHEALTHY,
        last_check_at=now - 301.0,
        unhealthy_recheck_attempts=0,
    )
    assert checker.should_check(proxy, now) is True


def test_unhealthy_exponential_backoff():
    config = ProxyForgeConfig(
        unhealthy_check_interval=300.0,
        unhealthy_backoff_factor=2.0,
        unhealthy_check_max_interval=3600.0,
    )
    checker = HealthChecker(config)
    now = 1000.0
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        status=ProxyStatus.UNHEALTHY,
        last_check_at=900.0,
        unhealthy_recheck_attempts=1,
    )
    assert checker.unhealthy_recheck_delay(proxy) == 600.0
    assert checker.should_check(proxy, now) is False
    assert checker.should_check(proxy, 1501.0) is True


def test_unhealthy_recovery_on_success():
    proxy = Proxy(host="1.1.1.1", port=8080, status=ProxyStatus.UNHEALTHY)
    proxy.unhealthy_at = time.time()
    proxy.unhealthy_recheck_attempts = 2
    proxy.record_success(100.0)
    assert proxy.status == ProxyStatus.HEALTHY
    assert proxy.unhealthy_at is None
    assert proxy.unhealthy_recheck_attempts == 0


def test_unhealthy_failed_recheck_increments_attempts():
    proxy = Proxy(host="1.1.1.1", port=8080, status=ProxyStatus.UNHEALTHY)
    proxy.consecutive_failures = 1
    proxy.record_failure(max_consecutive_failures=5)
    assert proxy.status == ProxyStatus.UNHEALTHY
    assert proxy.unhealthy_recheck_attempts == 1


def test_should_skip_banned_during_cooldown():
    config = ProxyForgeConfig(banned_cooldown_seconds=300.0)
    checker = HealthChecker(config)
    now = 1000.0
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        status=ProxyStatus.BANNED,
        banned_at=900.0,
        last_check_at=900.0,
    )
    assert checker.should_check(proxy, now) is False


def test_should_check_banned_after_cooldown():
    config = ProxyForgeConfig(
        banned_cooldown_seconds=300.0,
        banned_check_interval=60.0,
    )
    checker = HealthChecker(config)
    now = 1300.0
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        status=ProxyStatus.BANNED,
        banned_at=900.0,
        last_check_at=1200.0,
    )
    assert checker.should_check(proxy, now) is True


@pytest.mark.asyncio
async def test_check_all_uses_shared_client_and_batches():
    config = ProxyForgeConfig(
        health_check_concurrency=2,
        health_check_batch_size=2,
        health_check_interval=60.0,
    )
    checker = HealthChecker(config)
    now = time.time()
    proxies = [
        Proxy(host="1.1.1.1", port=8080, status=ProxyStatus.HEALTHY, last_check_at=now),
        Proxy(host="2.2.2.2", port=8080, status=ProxyStatus.HEALTHY, last_check_at=now - 120),
        Proxy(
            host="3.3.3.3",
            port=8080,
            status=ProxyStatus.UNHEALTHY,
            last_check_at=now - 10,
        ),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("proxyforge.services.health.httpx.AsyncClient", return_value=mock_client):
        summary = await checker.check_all(proxies)

    assert summary.checked == 1
    assert summary.skipped == 2
    assert summary.passed == 1
    assert mock_client.get.await_count == 1


@pytest.mark.asyncio
async def test_check_all_force_checks_everything():
    config = ProxyForgeConfig(health_check_batch_size=10)
    checker = HealthChecker(config)
    now = time.time()
    proxies = [
        Proxy(host="1.1.1.1", port=8080, status=ProxyStatus.HEALTHY, last_check_at=now),
        Proxy(host="2.2.2.2", port=8080, status=ProxyStatus.HEALTHY, last_check_at=now),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("proxyforge.services.health.httpx.AsyncClient", return_value=mock_client):
        summary = await checker.check_all(proxies, force=True)

    assert summary.checked == 2
    assert summary.skipped == 0
    assert mock_client.get.await_count == 2
    for call in mock_client.get.await_args_list:
        assert "proxy" in call.kwargs
