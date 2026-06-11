"""Redis 分布式单 IP 限流（滑动窗口 QPS + 并发计数）。"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

try:
    from redis.exceptions import ResponseError as RedisResponseError
except ImportError:  # pragma: no cover
    RedisResponseError = Exception

if TYPE_CHECKING:
    from proxyforge.services.storage.redis import RedisStorage

logger = logging.getLogger(__name__)

_CHECK_CAPACITY_SCRIPT = """
local qps_key = KEYS[1]
local conc_key = KEYS[2]
local max_qps = tonumber(ARGV[1])
local max_conc = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local window_ms = tonumber(ARGV[4])

if max_conc > 0 then
    local conc = tonumber(redis.call("GET", conc_key) or "0")
    if conc >= max_conc then
        return 1
    end
end

if max_qps > 0 then
    redis.call("ZREMRANGEBYSCORE", qps_key, 0, now_ms - window_ms)
    if redis.call("ZCARD", qps_key) >= max_qps then
        return 1
    end
end

return 0
"""

_TRY_ACQUIRE_SCRIPT = """
local qps_key = KEYS[1]
local conc_key = KEYS[2]
local max_qps = tonumber(ARGV[1])
local max_conc = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local member = ARGV[4]
local window_ms = tonumber(ARGV[5])
local conc_ttl = tonumber(ARGV[6])

if max_conc > 0 then
    local conc = tonumber(redis.call("GET", conc_key) or "0")
    if conc >= max_conc then
        return 0
    end
end

if max_qps > 0 then
    redis.call("ZREMRANGEBYSCORE", qps_key, 0, now_ms - window_ms)
    if redis.call("ZCARD", qps_key) >= max_qps then
        return 0
    end
end

if max_conc > 0 then
    redis.call("INCR", conc_key)
    redis.call("EXPIRE", conc_key, conc_ttl)
end

if max_qps > 0 then
    redis.call("ZADD", qps_key, now_ms, member)
    redis.call("PEXPIRE", qps_key, window_ms + 1000)
end

return 1
"""

_RELEASE_CONCURRENT_SCRIPT = """
local conc_key = KEYS[1]
local val = tonumber(redis.call("GET", conc_key) or "0")
if val <= 1 then
    return redis.call("DEL", conc_key)
end
return redis.call("DECR", conc_key)
"""


class RedisRateLimiter:
    """基于 Redis 的全局 QPS 滑动窗口与并发连接限制。"""

    def __init__(
        self,
        storage: RedisStorage,
        *,
        max_qps: float = 0.0,
        max_concurrent: int = 0,
        window_seconds: float = 1.0,
        concurrent_ttl_seconds: int = 3600,
    ) -> None:
        self._storage = storage
        self.max_qps = max(0.0, max_qps)
        self.max_concurrent = max(0, max_concurrent)
        self.window_ms = max(1, int(window_seconds * 1000))
        self.concurrent_ttl_seconds = max(60, concurrent_ttl_seconds)
        client = storage.sync_client
        self._lua_enabled = self._probe_lua_support(client)
        self._check_script = None
        self._try_acquire_script = None
        self._release_script = None
        if self._lua_enabled:
            self._check_script = client.register_script(_CHECK_CAPACITY_SCRIPT)
            self._try_acquire_script = client.register_script(_TRY_ACQUIRE_SCRIPT)
            self._release_script = client.register_script(_RELEASE_CONCURRENT_SCRIPT)

    @staticmethod
    def _probe_lua_support(client) -> bool:
        try:
            client.execute_command("EVALSHA", "0" * 40, 0)
            return True
        except RedisResponseError as exc:
            if "unknown command" in str(exc).lower():
                return False
            return True

    def _disable_lua(self) -> None:
        self._lua_enabled = False

    @property
    def sync_client(self):
        return self._storage.sync_client

    @property
    def enabled(self) -> bool:
        return self.max_qps > 0 or self.max_concurrent > 0

    def _qps_key(self, proxy_key: str) -> str:
        return f"{self._storage.key_prefix}:drqps:{proxy_key}"

    def _conc_key(self, proxy_key: str) -> str:
        return f"{self._storage.key_prefix}:drconc:{proxy_key}"

    def is_at_capacity(self, proxy_key: str) -> bool:
        if not self.enabled:
            return False
        now_ms = int(time.time() * 1000)
        if self._lua_enabled:
            keys = [self._qps_key(proxy_key), self._conc_key(proxy_key)]
            args = [int(self.max_qps), self.max_concurrent, now_ms, self.window_ms]
            try:
                return bool(self._check_script(keys=keys, args=args))
            except RedisResponseError:
                self._disable_lua()
        return self._is_at_capacity_fallback(proxy_key, now_ms)

    def try_acquire(self, proxy_key: str) -> bool:
        if not self.enabled:
            return True
        now_ms = int(time.time() * 1000)
        member = uuid.uuid4().hex
        if self._lua_enabled:
            keys = [self._qps_key(proxy_key), self._conc_key(proxy_key)]
            args = [
                int(self.max_qps),
                self.max_concurrent,
                now_ms,
                member,
                self.window_ms,
                self.concurrent_ttl_seconds,
            ]
            try:
                return bool(self._try_acquire_script(keys=keys, args=args))
            except RedisResponseError:
                self._disable_lua()
        return self._try_acquire_fallback(proxy_key, now_ms, member)

    def release(self, proxy_key: str) -> None:
        if self.max_concurrent <= 0:
            return
        if self._lua_enabled:
            key = self._conc_key(proxy_key)
            try:
                self._release_script(keys=[key], args=[])
                return
            except RedisResponseError:
                self._disable_lua()
        self._release_fallback(proxy_key)

    def _is_at_capacity_fallback(self, proxy_key: str, now_ms: int) -> bool:
        client = self.sync_client
        if self.max_concurrent > 0:
            conc = int(client.get(self._conc_key(proxy_key)) or 0)
            if conc >= self.max_concurrent:
                return True
        if self.max_qps > 0:
            qps_key = self._qps_key(proxy_key)
            client.zremrangebyscore(qps_key, 0, now_ms - self.window_ms)
            if client.zcard(qps_key) >= int(self.max_qps):
                return True
        return False

    def _try_acquire_fallback(
        self, proxy_key: str, now_ms: int, member: str
    ) -> bool:
        if self._is_at_capacity_fallback(proxy_key, now_ms):
            return False
        client = self.sync_client
        if self.max_concurrent > 0:
            conc_key = self._conc_key(proxy_key)
            client.incr(conc_key)
            client.expire(conc_key, self.concurrent_ttl_seconds)
        if self.max_qps > 0:
            qps_key = self._qps_key(proxy_key)
            client.zadd(qps_key, {member: now_ms})
            client.pexpire(qps_key, self.window_ms + 1000)
        return True

    def _release_fallback(self, proxy_key: str) -> None:
        client = self.sync_client
        conc_key = self._conc_key(proxy_key)
        val = int(client.get(conc_key) or 0)
        if val <= 1:
            client.delete(conc_key)
        else:
            client.decr(conc_key)
