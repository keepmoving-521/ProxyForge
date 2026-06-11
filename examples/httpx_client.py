"""httpx 客户端示例。"""

import asyncio

from proxyforge import ProxyForgeConfig, ProxyPool
from proxyforge.integrations.httpx_client import ProxyForgeHttpxClient
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.providers.static import StaticListProvider


async def main() -> None:
    config = ProxyForgeConfig(
        lease_enabled=True,
        max_proxy_retries=2,
        retry_http_codes=frozenset({403, 429, 503}),
    )
    provider = StaticListProvider(lines=["127.0.0.1:7890"])
    pool = ProxyPool(config, providers=[provider])
    await pool.refresh_from_providers()

    pool.add_proxy(
        Proxy(host="127.0.0.1", port=7890, score=90.0, status=ProxyStatus.HEALTHY)
    )

    async with ProxyForgeHttpxClient(pool, strategy="weighted") as client:
        response = await client.get("http://httpbin.org/ip")
        print(f"Status: {response.status_code}")
        print(response.text[:200])

    print(f"Pool stats: {pool.stats()}")


if __name__ == "__main__":
    asyncio.run(main())
