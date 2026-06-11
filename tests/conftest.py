"""共享 pytest fixtures。"""

import pytest

from proxyforge.config import ProxyForgeConfig
from proxyforge.models import Proxy
from proxyforge.pool import ProxyPool
from proxyforge.services.storage.redis import RedisStorage


@pytest.fixture
def shared_storage():
    fakeredis = pytest.importorskip("fakeredis")
    server = fakeredis.FakeServer()
    async_client = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    sync_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    store = RedisStorage(
        client=async_client,
        sync_client=sync_client,
        key_prefix="test",
    )
    yield store


def make_pool(
    *proxies: Proxy,
    storage: RedisStorage | None = None,
    **config_kwargs,
) -> ProxyPool:
    config = ProxyForgeConfig(min_score=0.0, **config_kwargs)
    pool = ProxyPool(config, storage=storage)
    for proxy in proxies:
        pool.add_proxy(proxy)
    return pool


def make_distributed_pool(
    storage: RedisStorage,
    *,
    instance_id: str,
    proxies: list[Proxy] | None = None,
    auto_persist: bool = False,
    **config_kwargs,
) -> ProxyPool:
    config = ProxyForgeConfig(
        lease_enabled=True,
        distributed_enabled=True,
        instance_id=instance_id,
        min_score=0.0,
        **config_kwargs,
    )
    pool = ProxyPool(config=config, storage=storage, auto_persist=auto_persist)
    for proxy in proxies or []:
        pool.add_proxy(proxy)
    return pool
