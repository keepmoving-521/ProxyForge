# ProxyForge

ProxyForge 是一个轻量级、高可用的代理池管理与调度框架。它专注于代理 IP 的健康检测、动态评分与智能路由。通过无缝对接各类合规的第三方代理服务商，ProxyForge 能够为高并发爬虫提供稳定、安全的网络基础设施。

## 特性

- **代理池管理** — 聚合多来源代理，统一增删与状态追踪
- **健康检测** — 异步并发检测可用性与响应延迟
- **动态评分** — 基于成功率与延迟的综合得分
- **智能路由** — 支持最优、加权随机、轮询等调度策略
- **HTTP API Provider** — 对接第三方代理 API（JSON / 纯文本）
- **Redis 持久化** — 代理状态跨进程/重启恢复
- **框架集成** — Scrapy 中间件、aiohttp 客户端封装

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
| `min_score` | 最低可用评分 | 20 |

示例配置见 [examples/config.example.yaml](examples/config.example.yaml)。

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

## Scrapy 集成

```python
# settings.py
PROXYFORGE_POOL = pool
PROXYFORGE_STRATEGY = "weighted"

DOWNLOADER_MIDDLEWARES = {
    "proxyforge.integrations.scrapy.ProxyForgeMiddleware": 350,
}
```

中间件会自动设置 `request.meta["proxy"]`，并根据响应状态上报成功/失败以更新评分。

## aiohttp 集成

```python
from proxyforge.integrations.aiohttp import ProxyForgeClient

async with ProxyForgeClient(pool, strategy="weighted") as client:
    response = await client.get("https://example.com")
    print(await response.text())
```

## 命令行

```bash
proxyforge check 127.0.0.1:7890 192.168.1.100:8080
proxyforge stats 127.0.0.1:7890
```

## 架构

```
proxyforge/
├── models.py           # 代理数据模型
├── pool.py             # 代理池核心
├── health.py           # 健康检测
├── scoring.py          # 动态评分
├── router.py           # 智能路由
├── serialization.py    # 序列化
├── config.py           # 配置
├── providers/          # 服务商接入
│   ├── base.py
│   ├── static.py
│   └── http_api.py
├── storage/            # 持久化
│   ├── base.py
│   └── redis.py
└── integrations/       # 框架集成
    ├── scrapy.py
    └── aiohttp.py
```

## 开发

```bash
pip install -e ".[all]"
pytest
```

## License

MIT
