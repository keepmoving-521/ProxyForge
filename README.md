# ProxyForge

ProxyForge 是一个轻量级、高可用的代理池管理与调度框架。它专注于代理 IP 的健康检测、动态评分与智能路由。通过无缝对接各类合规的第三方代理服务商，ProxyForge 能够为高并发爬虫提供稳定、安全的网络基础设施。

## 特性

- **代理池管理** — 聚合多来源代理，统一增删与状态追踪
- **健康检测** — 异步并发检测可用性与响应延迟
- **动态评分** — 基于成功率与延迟的综合得分
- **智能路由** — 支持最优、加权随机、轮询等调度策略
- **HTTP API Provider** — 对接第三方代理 API（JSON / 纯文本）
- **Redis 持久化** — 代理状态跨进程/重启恢复
- **框架集成** — Scrapy 中间件（失败换 IP）、httpx / aiohttp 客户端
- **代理租约** — 防止同一 IP 被并发重复使用

## 安装

```bash
# 基础安装
pip install -e .

# 含开发依赖
pip install -e ".[dev]"

# 按需安装扩展
pip install -e ".[redis]"       # Redis 持久化
pip install -e ".[aiohttp]"     # aiohttp 集成
pip install -e ".[scrapy]"      # Scrapy 中间件
pip install -e ".[all]"         # 全部扩展
```

## 配置

支持代码、环境变量、YAML 三种方式：

```python
from proxyforge import ProxyForgeConfig

# 直接构造
config = ProxyForgeConfig(max_consecutive_failures=5, allow_unknown_proxies=False)

# 环境变量 PROXYFORGE_MAX_CONSECUTIVE_FAILURES=5 等
config = ProxyForgeConfig.from_env()

# YAML 文件
config = ProxyForgeConfig.from_yaml("config.yaml")
```

关键配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `max_consecutive_failures` | 连续失败达阈值后封禁 | 3 |
| `banned_cooldown_seconds` | 封禁冷却时间（秒） | 300 |
| `allow_unknown_proxies` | 是否调度未检测代理 | true |
| `lease_enabled` | 是否启用代理租约 | true |
| `lease_ttl_seconds` | 租约 TTL（秒） | 60 |
| `max_proxy_retries` | 失败换 IP 最大重试次数 | 3 |
| `retry_http_codes` | 触发换 IP 的 HTTP 状态码 | 403,429,502,503,504 |
| `score_window_enabled` | 启用滑动窗口评分 | true |
| `score_window_seconds` | 评分窗口时长（秒） | 3600 |
| `score_window_max_events` | 窗口内最多保留事件数 | 500 |
| `persist_batch_size` | 持久化批量 flush 大小 | 10 |
| `persist_sync_fallback` | 无事件循环时使用同步 Redis | true |
| `distributed_enabled` | 启用 Redis 分布式租约（需 RedisStorage） | false |
| `distributed_sync_on_acquire` | 获取租约前从 Redis 同步评分/状态 | true |
| `instance_id` | 分布式实例标识（租约 owner） | 随机 12 位 hex |
| `rate_limit_enabled` | 启用单 IP QPS / 并发限流 | false |
| `max_qps_per_proxy` | 每 IP 每秒最大请求数 | 5 |
| `max_concurrent_per_proxy` | 每 IP 最大并发连接数 | 2 |
| `min_score` | 最低可用评分 | 20 |
| `health_check_concurrency` | 健康检测并发数 | 20 |
| `health_check_batch_size` | 分批检测每批大小 | 100 |
| `unhealthy_check_interval` | UNHEALTHY 复检基础间隔（秒） | 300 |
| `unhealthy_backoff_factor` | UNHEALTHY 指数退避倍数 | 2.0 |
| `unhealthy_check_max_interval` | UNHEALTHY 最大复检间隔（秒） | 3600 |
| `banned_check_interval` | BANNED 冷却后再检间隔（秒） | 300 |

示例配置见 [examples/config.example.yaml](examples/config.example.yaml)。

### 健康检测 URL（按标签 / 任务 / Spider）

```python
config = ProxyForgeConfig(
    health_check_url="http://httpbin.org/ip",
    health_check_urls_by_tag={"cn": "https://www.baidu.com/"},
    health_check_urls_by_task={"amazon": "https://www.amazon.com/robots.txt"},
    health_check_urls_by_spider={"news_spider": "https://news.example.com/health"},
)

# 按 spider 检测
await pool.check_health(spider="news_spider")

# 按任务检测
await pool.check_health(task="amazon")

# 代理自带标签时，自动匹配 health_check_urls_by_tag
proxy = Proxy(host="1.1.1.1", port=8080, tags=frozenset({"cn"}))

# 单代理 metadata 可覆盖
proxy.metadata["health_check_url"] = "https://target.com/ping"
```

解析优先级：**task → spider → 上下文 tags → 代理 tags → metadata → 默认 URL**。

## 快速开始

```python
import asyncio
from proxyforge import ProxyForgeConfig, ProxyPool
from proxyforge.providers.static import StaticListProvider

async def main():
    config = ProxyForgeConfig(health_check_url="http://httpbin.org/ip")
    provider = StaticListProvider(lines=["127.0.0.1:7890"])
    pool = ProxyPool(config, providers=[provider])

    await pool.refresh_from_providers()
    await pool.check_health()

    proxy = pool.acquire(strategy="weighted")
    print(proxy.url)

asyncio.run(main())
```

## HTTP API Provider

```python
from proxyforge import ProxyPool
from proxyforge.providers.http_api import HttpApiProvider, JsonFieldMapping

provider = HttpApiProvider(
    "https://vendor.example.com/api/proxies",
    headers={"Authorization": "Bearer TOKEN"},
    items_path="data.list",
    field_mapping=JsonFieldMapping(host="ip", port="port"),
    tags=frozenset({"vendor_a"}),
)
pool = ProxyPool(providers=[provider])
await pool.refresh_from_providers()
```

支持 `response_format="text"` 纯文本（每行 `host:port`），以及 JSON 字符串列表、对象列表、单字段 `proxy` 映射。

## Redis 持久化

```python
from proxyforge import ProxyPool
from proxyforge.storage.redis import RedisStorage

storage = RedisStorage(url="redis://localhost:6379/0")
pool = ProxyPool(storage=storage, auto_persist=True)

await pool.load()          # 启动时恢复
await pool.check_health()  # 检测后自动持久化
await pool.persist()       # 手动保存
await storage.close()
```

### 分布式调度（多进程 / 多机）

启用 `distributed_enabled` 后，租约通过 Redis `SETNX + TTL` 在实例间互斥；`acquire_lease` 会跳过已被其他进程占用的 IP，并在获取前可选地从 Redis 同步全局评分与运行时状态。

```python
from proxyforge import ProxyForgeConfig, ProxyPool
from proxyforge.storage.redis import RedisStorage

config = ProxyForgeConfig(
    lease_enabled=True,
    distributed_enabled=True,
    instance_id="worker-1",  # 每个进程/机器唯一
)
storage = RedisStorage(url="redis://localhost:6379/0")
pool = ProxyPool(config, storage=storage, auto_persist=True)

await pool.load()
lease = pool.acquire_lease(strategy="best")
try:
    ...
finally:
    pool.release_lease(lease)
```

## 单 IP 限流

在租约之上限制每个 IP 的 QPS 与并发连接数，避免请求过快被封。`acquire_lease` 会自动跳过已达上限的 IP，并在 `release_lease` 时释放并发配额。

单机部署使用进程内计数；**启用 `distributed_enabled` 且配置 `RedisStorage` 时**，限流自动切换为 Redis 滑动窗口（QPS）+ 全局并发计数，与分布式租约共用 `{prefix}:drqps:*` / `{prefix}:drconc:*` 键前缀。

```python
config = ProxyForgeConfig(
    lease_enabled=True,
    rate_limit_enabled=True,
    distributed_enabled=True,      # 多机时启用 Redis 全局限流
    max_qps_per_proxy=5.0,         # 每秒最多 5 次（全局）
    max_concurrent_per_proxy=2,    # 同时最多 2 个在途请求（全局）
)
storage = RedisStorage(url="redis://localhost:6379/0")
pool = ProxyPool(config, storage=storage)
```

## Scrapy 集成

```python
# settings.py
PROXYFORGE_POOL = pool
PROXYFORGE_STRATEGY = "weighted"
PROXYFORGE_MAX_RETRIES = 3
PROXYFORGE_RETRY_HTTP_CODES = [403, 429, 503]

DOWNLOADER_MIDDLEWARES = {
    "proxyforge.integrations.scrapy.ProxyForgeMiddleware": 350,
}
```

中间件自动分配代理租约，上报成功/失败；遇到 403/429/5xx 或网络异常时自动换 IP 重试。

## aiohttp 集成

```python
from proxyforge.integrations.aiohttp import ProxyForgeClient

async with ProxyForgeClient(pool, strategy="weighted") as client:
    response = await client.get("https://example.com")
    print(await response.text())
```

## httpx 集成

```python
from proxyforge.integrations.httpx_client import ProxyForgeHttpxClient

async with ProxyForgeHttpxClient(pool, strategy="weighted") as client:
    response = await client.get("https://example.com")
    print(response.text)
```

示例见 [examples/httpx_client.py](examples/httpx_client.py)。

## 代理租约

```python
lease = pool.acquire_lease(strategy="weighted")
try:
    # 使用 lease.proxy.url 发起请求
    ...
    pool.report_success(lease.proxy, latency_ms=120)
finally:
    pool.release_lease(lease)
```

## 命令行

```bash
proxyforge check 127.0.0.1:7890 192.168.1.100:8080
proxyforge stats 127.0.0.1:7890
```

## 架构

```
proxyforge/
├── __init__.py              # 公共 API 导出
├── config.py                # 配置（env / YAML / dict）
├── exceptions.py            # 异常层次
├── models.py                # Proxy 数据模型
├── state.py                 # 代理状态合并（Provider / 运行时）
├── wiring.py                # 组件装配（分布式协调器、限流器）
├── pool.py                  # ProxyPool 编排入口
├── cli.py                   # 命令行工具
│
├── scheduling/              # 调度层
│   └── lease_acquisition.py # 租约获取编排（本地 + 分布式）
├── router.py                # 路由策略（best / weighted / round_robin）
├── lease.py                 # 租约模型与 LeaseManager
├── rate_limit.py            # 本地限流 + RateLimiter 协议
│
├── health.py                # 健康检测
├── health_urls.py           # 检测 URL 解析
├── scoring.py               # 动态评分
├── score_window.py          # 滑动窗口统计
├── serialization.py         # 持久化序列化
│
├── providers/               # 代理来源
│   ├── base.py
│   ├── static.py
│   └── http_api.py
│
├── storage/                 # 持久化与分布式协调
│   ├── base.py
│   ├── persist.py           # 批量 flush 缓冲
│   ├── redis.py             # Redis 存储
│   ├── redis_coordinator.py # 分布式租约（SETNX + TTL）
│   └── redis_rate_limit.py  # 分布式限流（滑动窗口 QPS）
│
└── integrations/            # 框架集成
    ├── scrapy.py
    ├── aiohttp.py
    └── httpx_client.py
```

**分层依赖：** `models` → `config` / `state` → `health` / `router` / `lease` / `rate_limit` / `storage` → `scheduling` → `pool` → `integrations`

**扩展点：**

| 需求 | 扩展方式 |
|------|----------|
| 新代理来源 | 继承 `BaseProvider` |
| 新存储后端 | 继承 `BaseStorage` |
| 自定义限流 / 分布式 | 构造 `ProxyPool` 时注入 `rate_limiter` / `distributed` |
| 新 HTTP 框架 | 参考 `integrations/httpx_client.py` 的 acquire → request → release 模式 |

## 开发

```bash
pip install -e ".[all]"
pytest
```

## License

MIT
