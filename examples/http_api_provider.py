"""HTTP API Provider 示例。"""

import asyncio

from proxyforge import ProxyPool
from proxyforge.providers.http_api import HttpApiProvider, JsonFieldMapping


async def main() -> None:
    # 示例：对接返回 {"data": {"proxies": [{"ip": "...", "port": ...}]}} 的 API
    provider = HttpApiProvider(
        "https://your-vendor.com/api/proxies",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        items_path="data.proxies",
        field_mapping=JsonFieldMapping(host="ip", port="port", protocol="type"),
        tags=frozenset({"vendor_a"}),
    )

    # 纯文本响应 API 示例
    # provider = HttpApiProvider(
    #     "https://your-vendor.com/api/proxies.txt",
    #     response_format="text",
    # )

    pool = ProxyPool(providers=[provider])
    count = await pool.refresh_from_providers()
    print(f"Fetched {count} proxies")


if __name__ == "__main__":
    asyncio.run(main())
