"""ProxyForge - 轻量级、高可用的代理池管理与调度框架。"""

from proxyforge.config import ProxyForgeConfig
from proxyforge.lease import ProxyLease
from proxyforge.models import Proxy, ProxyProtocol, ProxyStatus
from proxyforge.pool import ProxyPool
from proxyforge.router import ProxyRouter

__all__ = [
    "Proxy",
    "ProxyProtocol",
    "ProxyStatus",
    "ProxyLease",
    "ProxyPool",
    "ProxyRouter",
    "ProxyForgeConfig",
    "__version__",
]

__version__ = "0.3.0"
