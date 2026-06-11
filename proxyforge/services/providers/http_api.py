"""HTTP API 代理服务商。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from proxyforge.exceptions import ProviderError
from proxyforge.models import Proxy, ProxyProtocol
from proxyforge.services.providers.base import BaseProvider
from proxyforge.services.providers.static import parse_proxy_lines

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class JsonFieldMapping:
    """JSON 响应字段映射。"""

    host: str = "host"
    port: str = "port"
    protocol: str = "protocol"
    username: str = "username"
    password: str = "password"
    tags: str = "tags"
    proxy: str | None = None  # 单字段 "host:port" 或完整 URL


def _get_by_path(data: Any, path: str | None) -> Any:
    if path is None or path == "":
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            return None
    return current


def _get_field(item: dict[str, Any], field: str) -> Any:
    if "." in field:
        return _get_by_path(item, field)
    return item.get(field)


class HttpApiProvider(BaseProvider):
    """从 HTTP API 拉取代理列表，支持 JSON 与纯文本响应。"""

    name = "http_api"

    def __init__(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        response_format: str = "json",
        items_path: str | None = None,
        field_mapping: JsonFieldMapping | None = None,
        default_protocol: ProxyProtocol = ProxyProtocol.HTTP,
        provider_name: str = "http_api",
        timeout: float = 30.0,
        tags: frozenset[str] | None = None,
    ) -> None:
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.params = params
        self.json_body = json_body
        self.response_format = response_format
        self.items_path = items_path
        self.field_mapping = field_mapping or JsonFieldMapping()
        self.default_protocol = default_protocol
        self.provider_name = provider_name
        self.timeout = timeout
        self.tags = tags or frozenset()

    async def fetch_proxies(self) -> list[Proxy]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    self.method,
                    self.url,
                    headers=self.headers,
                    params=self.params,
                    json=self.json_body,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"HTTP API request failed: {exc}") from exc

        if self.response_format == "text":
            lines = response.text.splitlines()
            proxies = parse_proxy_lines(
                lines, self.default_protocol, self.provider_name
            )
        else:
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise ProviderError("Invalid JSON response from proxy API") from exc
            proxies = self._parse_json(payload)

        if self.tags:
            for proxy in proxies:
                proxy.tags = proxy.tags | self.tags
        return proxies

    def _parse_json(self, payload: Any) -> list[Proxy]:
        items = _get_by_path(payload, self.items_path)
        if items is None:
            items = payload
        if not isinstance(items, list):
            raise ProviderError("Proxy API response is not a list")

        mapping = self.field_mapping
        result: list[Proxy] = []

        for item in items:
            if isinstance(item, str):
                parsed = parse_proxy_lines(
                    [item], self.default_protocol, self.provider_name
                )
                if parsed:
                    result.extend(parsed)
                continue

            if not isinstance(item, dict):
                logger.debug("Skip unsupported proxy item: %r", item)
                continue

            if mapping.proxy:
                raw = _get_field(item, mapping.proxy)
                if raw:
                    parsed = parse_proxy_lines(
                        [str(raw)], self.default_protocol, self.provider_name
                    )
                    if parsed:
                        result.extend(parsed)
                    continue

            host = _get_field(item, mapping.host)
            port = _get_field(item, mapping.port)
            if not host or port is None:
                logger.debug("Skip item missing host/port: %r", item)
                continue

            protocol_raw = _get_field(item, mapping.protocol)
            protocol = (
                ProxyProtocol(str(protocol_raw).lower())
                if protocol_raw
                else self.default_protocol
            )
            tags_raw = _get_field(item, mapping.tags)
            item_tags = frozenset(tags_raw) if tags_raw else frozenset()

            result.append(
                Proxy(
                    host=str(host),
                    port=int(port),
                    protocol=protocol,
                    username=_optional_str(_get_field(item, mapping.username)),
                    password=_optional_str(_get_field(item, mapping.password)),
                    provider=self.provider_name,
                    tags=item_tags,
                )
            )
        return result


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
