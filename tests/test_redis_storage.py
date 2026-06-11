"""Redis 存储测试。"""

import json

import pytest

fakeredis = pytest.importorskip("fakeredis")

from proxyforge.models import Proxy, ProxyStatus
from proxyforge.services.storage.redis import RedisStorage


@pytest.fixture
async def storage():
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    store = RedisStorage(client=client, key_prefix="test")
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_redis_save_and_load(storage):
    p1 = Proxy(host="1.1.1.1", port=8080, score=90.0, status=ProxyStatus.HEALTHY)
    p2 = Proxy(host="2.2.2.2", port=9090, score=70.0, status=ProxyStatus.HEALTHY)

    await storage.save_all([p1, p2])
    loaded = await storage.load_all()

    assert len(loaded) == 2
    keys = {p.key for p in loaded}
    assert p1.key in keys
    assert p2.key in keys


@pytest.mark.asyncio
async def test_redis_save_proxy_updates_single(storage):
    proxy = Proxy(host="3.3.3.3", port=8080, score=50.0)
    await storage.save_proxy(proxy)
    proxy.score = 95.0
    proxy.status = ProxyStatus.HEALTHY
    await storage.save_proxy(proxy)

    loaded = await storage.load_all()
    assert len(loaded) == 1
    assert loaded[0].score == 95.0


@pytest.mark.asyncio
async def test_redis_delete_and_clear(storage):
    proxy = Proxy(host="4.4.4.4", port=8080)
    await storage.save_proxy(proxy)
    await storage.delete_proxy(proxy.key)
    assert await storage.load_all() == []

    await storage.save_proxy(proxy)
    await storage.clear()
    assert await storage.load_all() == []


@pytest.mark.asyncio
async def test_pool_load_and_persist(storage):
    from proxyforge.pool import ProxyPool

    pool = ProxyPool(storage=storage, auto_persist=True)
    pool.add_proxy(Proxy(host="5.5.5.5", port=8080, score=80.0))

    await pool.persist()

    pool2 = ProxyPool(storage=storage)
    count = await pool2.load()
    assert count == 1
    assert pool2.total_count == 1
