"""ProxyForge - 轻量级、高可用的代理池管理与调度框架。"""

from proxyforge.config import ProxyForgeConfig
from proxyforge.exceptions import (
    HealthCheckError,
    ProviderError,
    ProxyForgeError,
    ProxyNotAvailableError,
)
from proxyforge.lease import ProxyLease
from proxyforge.models import Proxy, ProxyProtocol, ProxyStatus
from proxyforge.pool import ProxyPool
from proxyforge.router import ProxyRouter
from proxyforge.scheduling import LeaseAcquisitionService
from proxyforge.services import (
    HealthCheckContext,
    HealthCheckSummary,
    HealthChecker,
    ProxyScorer,
    WindowStats,
)
from proxyforge.state import merge_provider_fields, merge_runtime_state

__all__ = [
    "HealthCheckContext",
    "HealthCheckSummary",
    "HealthChecker",
    "HealthCheckError",
    "LeaseAcquisitionService",
    "ProviderError",
    "Proxy",
    "ProxyForgeConfig",
    "ProxyForgeError",
    "ProxyLease",
    "ProxyNotAvailableError",
    "ProxyPool",
    "ProxyProtocol",
    "ProxyRouter",
    "ProxyScorer",
    "ProxyStatus",
    "WindowStats",
    "merge_provider_fields",
    "merge_runtime_state",
    "__version__",
]

__version__ = "0.3.0"
