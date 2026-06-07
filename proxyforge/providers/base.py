"""第三方代理服务商抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from proxyforge.models import Proxy


class BaseProvider(ABC):
    """合规第三方代理服务商接入接口。"""

    name: str = "base"

    @abstractmethod
    async def fetch_proxies(self) -> list[Proxy]:
        """从服务商拉取代理列表。"""
