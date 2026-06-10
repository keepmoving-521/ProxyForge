"""HTTP API Provider 测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from proxyforge.exceptions import ProviderError
from proxyforge.providers.http_api import HttpApiProvider, JsonFieldMapping


@pytest.mark.asyncio
async def test_http_api_json_list():
    payload = [
        {"ip": "1.1.1.1", "port": 8080},
        {"ip": "2.2.2.2", "port": 9090, "protocol": "socks5"},
    ]
    provider = HttpApiProvider(
        "http://api.example.com/proxies",
        field_mapping=JsonFieldMapping(host="ip", port="port"),
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("proxyforge.providers.http_api.httpx.AsyncClient", return_value=mock_client):
        proxies = await provider.fetch_proxies()

    assert len(proxies) == 2
    assert proxies[0].host == "1.1.1.1"
    assert proxies[1].protocol.value == "socks5"


@pytest.mark.asyncio
async def test_http_api_json_with_items_path():
    payload = {"data": {"list": ["3.3.3.3:3128", "4.4.4.4:8080"]}}
    provider = HttpApiProvider(
        "http://api.example.com/proxies",
        items_path="data.list",
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("proxyforge.providers.http_api.httpx.AsyncClient", return_value=mock_client):
        proxies = await provider.fetch_proxies()

    assert len(proxies) == 2
    assert proxies[0].host == "3.3.3.3"


@pytest.mark.asyncio
async def test_http_api_text_response():
    provider = HttpApiProvider(
        "http://api.example.com/proxies",
        response_format="text",
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "5.5.5.5:8888\n# comment\n6.6.6.6:9999"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("proxyforge.providers.http_api.httpx.AsyncClient", return_value=mock_client):
        proxies = await provider.fetch_proxies()

    assert len(proxies) == 2


@pytest.mark.asyncio
async def test_http_api_request_failure():
    provider = HttpApiProvider("http://api.example.com/proxies")

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("proxyforge.providers.http_api.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ProviderError):
            await provider.fetch_proxies()
