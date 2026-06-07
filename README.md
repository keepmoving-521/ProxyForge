# ProxyForge

ProxyForge 是一个轻量级、高可用的代理池管理与调度框架。它专注于代理 IP 的健康检测、动态评分与智能路由。通过无缝对接各类合规的第三方代理服务商，ProxyForge 能够为高并发爬虫提供稳定、安全的网络基础设施。

## 特性

- **代理池管理** — 聚合多来源代理，统一增删与状态追踪
- **健康检测** — 异步并发检测可用性与响应延迟
- **动态评分** — 基于成功率与延迟的综合得分
- **智能路由** — 支持最优、加权随机、轮询等调度策略
- **服务商接入** — 抽象 Provider 接口，便于对接第三方代理 API

## 安装

```bash
pip install -e ".[dev]"
```

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

更多示例见 [examples/basic_usage.py](examples/basic_usage.py)。

## 命令行

```bash
# 检测代理健康
proxyforge check 127.0.0.1:7890 192.168.1.100:8080

# 查看代理池统计
proxyforge stats 127.0.0.1:7890
```

## 架构

```
proxyforge/
├── models.py      # 代理数据模型
├── pool.py        # 代理池核心
├── health.py      # 健康检测
├── scoring.py     # 动态评分
├── router.py      # 智能路由
├── config.py      # 配置
└── providers/     # 第三方服务商接入
    ├── base.py
    └── static.py
```

## 自定义 Provider

```python
from proxyforge.models import Proxy
from proxyforge.providers.base import BaseProvider

class MyProvider(BaseProvider):
    name = "my_vendor"

    async def fetch_proxies(self) -> list[Proxy]:
        # 调用第三方 API 获取代理列表
        ...
```

## 开发

```bash
pytest
```

## License

MIT
