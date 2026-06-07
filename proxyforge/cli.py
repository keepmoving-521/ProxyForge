"""ProxyForge 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from proxyforge.config import ProxyForgeConfig
from proxyforge.pool import ProxyPool
from proxyforge.providers.static import StaticListProvider


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proxyforge",
        description="ProxyForge - 代理池管理与调度",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出调试日志",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="检测代理健康状态")
    check.add_argument(
        "proxies",
        nargs="+",
        help="代理地址，格式 host:port 或 protocol://host:port",
    )
    check.add_argument(
        "--url",
        default="http://httpbin.org/ip",
        help="健康检测目标 URL",
    )
    check.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="请求超时（秒）",
    )

    stats = sub.add_parser("stats", help="显示代理池统计（需配合 Python API）")
    stats.add_argument(
        "proxies",
        nargs="+",
        help="代理地址列表",
    )

    return parser


async def _cmd_check(args: argparse.Namespace) -> int:
    config = ProxyForgeConfig(
        health_check_url=args.url,
        health_check_timeout=args.timeout,
    )
    provider = StaticListProvider(lines=args.proxies)
    pool = ProxyPool(config, providers=[provider])
    await pool.refresh_from_providers()
    results = await pool.check_health()

    for proxy in pool.proxies:
        ok = results.get(proxy.key, False)
        status = "OK" if ok else "FAIL"
        print(
            f"[{status}] {proxy.key}  score={proxy.score:.1f}  "
            f"latency={proxy.avg_latency_ms:.0f}ms"
        )

    healthy = sum(1 for v in results.values() if v)
    print(f"\nHealthy: {healthy}/{len(results)}")
    return 0 if healthy else 1


async def _cmd_stats(args: argparse.Namespace) -> int:
    provider = StaticListProvider(lines=args.proxies)
    pool = ProxyPool(providers=[provider])
    await pool.refresh_from_providers()
    print(json.dumps(pool.stats(), indent=2, ensure_ascii=False))
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    if args.command == "check":
        return await _cmd_check(args)
    if args.command == "stats":
        return await _cmd_stats(args)
    return 1


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    code = asyncio.run(_async_main(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
