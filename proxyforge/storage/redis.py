"""Redis 持久化存储。"""

from __future__ import annotations

import json
import logging
from typing import Iterable

from proxyforge.models import Proxy
from proxyforge.serialization import proxy_from_dict, proxy_to_dict
from proxyforge.storage.base import BaseStorage

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover - optional dependency
    aioredis = None  # type: ignore[assignment]


class RedisStorage(BaseStorage):
    """使用 Redis 持久化代理池状态。"""

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        key_prefix: str = "proxyforge",
        client: aioredis.Redis | None = None,
    ) -> None:
        if aioredis is None:
            raise ImportError(
                "redis package is required for RedisStorage. "
                "Install with: pip install proxyforge[redis]"
            )
        self.url = url
        self.key_prefix = key_prefix
        self._client = client
        self._owns_client = client is None

    @property
    def _index_key(self) -> str:
        return f"{self.key_prefix}:proxies"

    def _proxy_key(self, key: str) -> str:
        return f"{self.key_prefix}:proxy:{key}"

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self.url, decode_responses=True)
        return self._client

    async def close(self) -> None:
        if self._client and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def save_proxy(self, proxy: Proxy) -> None:
        client = await self._get_client()
        payload = json.dumps(proxy_to_dict(proxy), ensure_ascii=False)
        pipe = client.pipeline()
        pipe.set(self._proxy_key(proxy.key), payload)
        pipe.sadd(self._index_key, proxy.key)
        await pipe.execute()

    async def save_all(self, proxies: Iterable[Proxy]) -> None:
        client = await self._get_client()
        pipe = client.pipeline()
        keys: list[str] = []
        for proxy in proxies:
            payload = json.dumps(proxy_to_dict(proxy), ensure_ascii=False)
            pipe.set(self._proxy_key(proxy.key), payload)
            keys.append(proxy.key)
        if keys:
            pipe.delete(self._index_key)
            pipe.sadd(self._index_key, *keys)
        await pipe.execute()

    async def load_all(self) -> list[Proxy]:
        client = await self._get_client()
        keys = await client.smembers(self._index_key)
        if not keys:
            return []

        pipe = client.pipeline()
        for key in keys:
            pipe.get(self._proxy_key(key))
        values = await pipe.execute()

        proxies: list[Proxy] = []
        for key, raw in zip(keys, values):
            if not raw:
                await client.srem(self._index_key, key)
                continue
            try:
                proxies.append(proxy_from_dict(json.loads(raw)))
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("Skip corrupted proxy entry: %s", key)
        return proxies

    async def delete_proxy(self, key: str) -> None:
        client = await self._get_client()
        pipe = client.pipeline()
        pipe.delete(self._proxy_key(key))
        pipe.srem(self._index_key, key)
        await pipe.execute()

    async def clear(self) -> None:
        client = await self._get_client()
        keys = await client.smembers(self._index_key)
        if not keys:
            return
        pipe = client.pipeline()
        for key in keys:
            pipe.delete(self._proxy_key(key))
        pipe.delete(self._index_key)
        await pipe.execute()
