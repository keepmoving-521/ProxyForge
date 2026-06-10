"""aiohttp 集成测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

aiohttp = pytest.importorskip("aiohttp")

from proxyforge.integrations.aiohttp import ProxyForgeClient
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool


@pytest.mark.asyncio
async def test_aiohttp_client_injects_proxy_and_reports():
    pool = ProxyPool()
    proxy = Proxy(host="1.2.3.4", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)

    mock_response = MagicMock()
    mock_response.status = 200

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(return_value=mock_response)
    mock_session.close = AsyncMock()

    client = ProxyForgeClient(pool, session=mock_session)
    async with client:
        response = await client.get("http://example.com")

    assert response.status == 200
    mock_session.request.assert_awaited_once()
    call_kwargs = mock_session.request.await_args.kwargs
    assert call_kwargs["proxy"] == proxy.url
    assert proxy.success_count == 1


@pytest.mark.asyncio
async def test_aiohttp_client_reports_failure_on_exception():
    pool = ProxyPool()
    proxy = Proxy(host="1.2.3.4", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(side_effect=aiohttp.ClientError("network"))
    mock_session.close = AsyncMock()

    client = ProxyForgeClient(pool, session=mock_session)
    async with client:
        with pytest.raises(aiohttp.ClientError):
            await client.get("http://example.com")

    assert proxy.failure_count == 1
