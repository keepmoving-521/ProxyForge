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
    import redis
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover - optional dependency
    redis = None  # type: ignore[assignment]
    aioredis = None  # type: ignore[assignment]


class RedisStorage(BaseStorage):
    """使用 Redis 持久化代理池状态。"""

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        key_prefix: str = "proxyforge",
        client: aioredis.Redis | None = None,
        sync_client: redis.Redis | None = None,
    ) -> None:
        if aioredis is None or redis is None:
            raise ImportError(
                "redis package is required for RedisStorage. "
                "Install with: pip install proxyforge[redis]"
            )
        self.url = url
        self.key_prefix = key_prefix
        self._client = client
        self._sync_client = sync_client
        self._owns_client = client is None
        self._owns_sync_client = sync_client is None

    @property
    def _index_key(self) -> str:
        return f"{self.key_prefix}:proxies"

    def _proxy_key(self, key: str) -> str:
        return f"{self.key_prefix}:proxy:{key}"

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self.url, decode_responses=True)
        return self._client

    def _get_sync_client(self) -> redis.Redis:
        if self._sync_client is None:
            self._sync_client = redis.from_url(self.url, decode_responses=True)
        return self._sync_client

    async def close(self) -> None:
        if self._client and self._owns_client:
            await self._client.aclose()
            self._client = None
        if self._sync_client and self._owns_sync_client:
            self._sync_client.close()
            self._sync_client = None

    def supports_sync(self) -> bool:
        return True

    def _encode_proxy(self, proxy: Proxy) -> str:
        return json.dumps(proxy_to_dict(proxy), ensure_ascii=False)

    async def save_proxy(self, proxy: Proxy) -> None:
        await self.save_proxies_batch([proxy])

    async def save_proxies_batch(self, proxies: Iterable[Proxy]) -> None:
        client = await self._get_client()
        pipe = client.pipeline()
        has_items = False
        for proxy in proxies:
            has_items = True
            pipe.set(self._proxy_key(proxy.key), self._encode_proxy(proxy))
            pipe.sadd(self._index_key, proxy.key)
        if has_items:
            await pipe.execute()

    def save_proxy_sync(self, proxy: Proxy) -> None:
        self.save_proxies_sync([proxy])

    def save_proxies_sync(self, proxies: Iterable[Proxy]) -> None:
        client = self._get_sync_client()
        pipe = client.pipeline()
        has_items = False
        for proxy in proxies:
            has_items = True
            pipe.set(self._proxy_key(proxy.key), self._encode_proxy(proxy))
            pipe.sadd(self._index_key, proxy.key)
        if has_items:
            pipe.execute()

    async def save_all(self, proxies: Iterable[Proxy]) -> None:
        client = await self._get_client()
        pipe = client.pipeline()
        keys: list[str] = []
        for proxy in proxies:
            pipe.set(self._proxy_key(proxy.key), self._encode_proxy(proxy))
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
