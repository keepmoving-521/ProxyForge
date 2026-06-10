"""aiohttp 集成示例。"""

import asyncio

from proxyforge import ProxyPool
from proxyforge.integrations.aiohttp import ProxyForgeClient
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.providers.static import StaticListProvider


async def main() -> None:
    provider = StaticListProvider(lines=["127.0.0.1:7890"])
    pool = ProxyPool(providers=[provider])
    await pool.refresh_from_providers()

    proxy = Proxy(host="127.0.0.1", port=7890, score=90.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)

    async with ProxyForgeClient(pool, strategy="weighted") as client:
        response = await client.get("http://httpbin.org/ip")
        print(f"Status: {response.status}")
        text = await response.text()
        print(text[:200])

    print(f"Pool stats: {pool.stats()}")


if __name__ == "__main__":
    asyncio.run(main())
