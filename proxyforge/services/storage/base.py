"""存储抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from proxyforge.models import Proxy


class BaseStorage(ABC):
    """代理池持久化存储接口。"""

    @abstractmethod
    async def save_proxy(self, proxy: Proxy) -> None:
        """保存单个代理状态。"""

    @abstractmethod
    async def save_proxies_batch(self, proxies: Iterable[Proxy]) -> None:
        """批量保存部分代理（不重建索引）。"""

    @abstractmethod
    async def save_all(self, proxies: Iterable[Proxy]) -> None:
        """批量保存代理。"""

    @abstractmethod
    async def load_all(self) -> list[Proxy]:
        """加载全部代理。"""

    @abstractmethod
    async def delete_proxy(self, key: str) -> None:
        """删除代理。"""

    @abstractmethod
    async def clear(self) -> None:
        """清空存储。"""

    def supports_sync(self) -> bool:
        return False

    def save_proxy_sync(self, proxy: Proxy) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not support sync persist")

    def save_proxies_sync(self, proxies: Iterable[Proxy]) -> None:
        for proxy in proxies:
            self.save_proxy_sync(proxy)
