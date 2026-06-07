"""代理服务商抽象接口。"""

from proxyforge.providers.base import BaseProvider
from proxyforge.providers.http_api import HttpApiProvider, JsonFieldMapping
from proxyforge.providers.static import StaticListProvider

__all__ = ["BaseProvider", "HttpApiProvider", "JsonFieldMapping", "StaticListProvider"]
