"""ProxyForge 异常定义。"""


class ProxyForgeError(Exception):
    """ProxyForge 基础异常。"""


class ProxyNotAvailableError(ProxyForgeError):
    """无可用代理时抛出。"""


class ProviderError(ProxyForgeError):
    """代理服务商接口异常。"""


class HealthCheckError(ProxyForgeError):
    """健康检测失败。"""
