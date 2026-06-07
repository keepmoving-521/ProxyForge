"""静态代理列表服务商（开发/测试用）。"""

from __future__ import annotations

from proxyforge.models import Proxy, ProxyProtocol
from proxyforge.providers.base import BaseProvider


class StaticListProvider(BaseProvider):
    """从预设列表或文本行提供代理。"""

    name = "static"

    def __init__(
        self,
        proxies: list[Proxy] | None = None,
        *,
        lines: list[str] | None = None,
        default_protocol: ProxyProtocol = ProxyProtocol.HTTP,
        provider_name: str = "static",
    ) -> None:
        self._proxies = list(proxies or [])
        if lines:
            self._proxies.extend(
                parse_proxy_lines(lines, default_protocol, provider_name)
            )

    async def fetch_proxies(self) -> list[Proxy]:
        return list(self._proxies)


def parse_proxy_lines(
    lines: list[str],
    default_protocol: ProxyProtocol = ProxyProtocol.HTTP,
    provider_name: str = "static",
) -> list[Proxy]:
    """解析 `host:port` 或 `protocol://host:port` 格式。"""
    result: list[Proxy] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        protocol = default_protocol
        body = line
        if "://" in line:
            scheme, body = line.split("://", 1)
            protocol = ProxyProtocol(scheme.lower())
        if "@" in body:
            auth, hostport = body.rsplit("@", 1)
            username, password = auth.split(":", 1)
        else:
            username = password = None
            hostport = body
        host, port_str = hostport.rsplit(":", 1)
        result.append(
            Proxy(
                host=host,
                port=int(port_str),
                protocol=protocol,
                username=username,
                password=password,
                provider=provider_name,
            )
        )
    return result
