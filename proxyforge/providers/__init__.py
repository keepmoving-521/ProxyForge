"""代理服务商抽象接口。"""

from proxyforge.providers.base import BaseProvider
from proxyforge.providers.static import StaticListProvider

__all__ = ["BaseProvider", "StaticListProvider"]
