"""ProxyForge 基础用法示例。"""

import asyncio

from proxyforge import ProxyForgeConfig, ProxyPool
from proxyforge.providers.static import StaticListProvider


async def main() -> None:
    config = ProxyForgeConfig(
        health_check_url="http://httpbin.org/ip",
        health_check_interval=30.0,
        min_score=30.0,
    )

    provider = StaticListProvider(
        lines=[
            "127.0.0.1:7890",
            "183.238.163.8:9002",
            "203.19.38.114:1080",
            "47.115.221.69:9090",
            "101.66.198.62:8085",
            # "192.168.1.100:8080",
        ],
        provider_name="local",
    )

    pool = ProxyPool(config, providers=[provider])
    await pool.refresh_from_providers()

    print(f"Loaded {pool.total_count} proxies")
    await pool.check_health()

    for proxy in pool.proxies:
        print(f"  {proxy.key}  status={proxy.status.value}  score={proxy.score:.1f}")

    if pool.healthy_count > 0:
        proxy = pool.acquire(strategy="weighted")
        print(f"\nAcquired proxy: {proxy.url}")
        pool.report_success(proxy, latency_ms=120.0)
    else:
        print("\nNo healthy proxy available.")

    print(f"\nPool stats: {pool.stats()}")


if __name__ == "__main__":
    asyncio.run(main())
