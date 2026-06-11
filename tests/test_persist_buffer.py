"""持久化 flush 队列测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

fakeredis = pytest.importorskip("fakeredis")

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy, ProxyStatus
from proxyforge.pool import ProxyPool
from proxyforge.storage.persist import PersistBuffer
from proxyforge.storage.redis import RedisStorage


def test_persist_buffer_sync_fallback_without_event_loop():
    storage = MagicMock()
    storage.supports_sync.return_value = True
    storage.save_proxies_sync = MagicMock()

    buffer = PersistBuffer(storage, batch_size=100, sync_fallback=True)
    proxy = Proxy(host="1.1.1.1", port=8080, score=80.0)
    buffer.mark_dirty(proxy)

    assert storage.save_proxies_sync.called
    assert buffer.pending_count == 0


@pytest.mark.asyncio
async def test_persist_buffer_async_flush():
    storage = AsyncMock()
    storage.supports_sync.return_value = False
    storage.save_proxies_batch = AsyncMock()

    buffer = PersistBuffer(storage, batch_size=100)
    proxy = Proxy(host="1.1.1.1", port=8080)
    buffer.mark_dirty(proxy)
    count = await buffer.flush_async()

    assert count == 1
    storage.save_proxies_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_buffer_batch_flush_at_threshold():
    storage = AsyncMock()
    storage.supports_sync.return_value = False
    storage.save_proxies_batch = AsyncMock()

    buffer = PersistBuffer(storage, batch_size=2, sync_fallback=True)
    buffer.mark_dirty(Proxy(host="1.1.1.1", port=8080))
    assert storage.save_proxies_batch.await_count == 0
    assert buffer.pending_count == 1

    buffer.mark_dirty(Proxy(host="2.2.2.2", port=8080))
    await asyncio.sleep(0)
    storage.save_proxies_batch.assert_awaited_once()
    assert buffer.pending_count == 0


def test_pool_report_failure_sync_persist():
    sync_client = fakeredis.FakeRedis(decode_responses=True)
    storage = RedisStorage(sync_client=sync_client, client=fakeredis.FakeAsyncRedis(decode_responses=True), key_prefix="sync")
    pool = ProxyPool(
        ProxyForgeConfig(persist_batch_size=1, persist_sync_fallback=True),
        storage=storage,
        auto_persist=True,
    )
    proxy = Proxy(host="1.1.1.1", port=8080, score=80.0, status=ProxyStatus.HEALTHY)
    pool.add_proxy(proxy)

    pool.report_failure(proxy)

    loaded = sync_client.get(storage._proxy_key(proxy.key))
    assert loaded is not None
    assert proxy.failure_count == 1


@pytest.mark.asyncio
async def test_pool_flush_persist_async():
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    storage = RedisStorage(client=client, key_prefix="flush")
    pool = ProxyPool(storage=storage, auto_persist=True)
    pool.add_proxy(Proxy(host="3.3.3.3", port=8080, score=70.0))
    pool._persist_buffer.mark_dirty(pool.proxies[0])

    count = await pool.flush_persist()
    assert count == 1
    assert pool._persist_buffer.pending_count == 0
