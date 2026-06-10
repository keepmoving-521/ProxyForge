"""Redis 持久化示例。"""

import asyncio

from proxyforge import ProxyForgeConfig, ProxyPool
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.storage.redis import RedisStorage


async def main() -> None:
    # storage = RedisStorage(url="redis://localhost:6379/0", key_prefix="proxyforge:demo")
    storage = RedisStorage(url="redis://:12345678@192.168.1.119:6379/0", key_prefix="proxyforge:demo")

    pool = ProxyPool(
        ProxyForgeConfig(health_check_url="http://httpbin.org/ip"),
        storage=storage,
        auto_persist=True,
    )

    # 启动时从 Redis 恢复
    loaded = await pool.load()
    print(f"Loaded {loaded} proxies from Redis")

    if pool.total_count == 0:
        pool.add_proxy(
            Proxy(host="127.0.0.1", port=7890, score=80.0, status=ProxyStatus.HEALTHY)
        )
        await pool.persist()
        print("Seeded initial proxy to Redis")

    await pool.check_health()
    print(f"Pool stats: {pool.stats()}")

    await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
