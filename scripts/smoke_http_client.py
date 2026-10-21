#!/usr/bin/env python3
"""驗收用腳本，不是自動化測試。

用官方 `mcp` SDK 的 `streamablehttp_client` 連到已經在跑的 seo-pulse streamable HTTP 伺服器
（先用另一個終端機執行 `seo-pulse serve --transport http`），印出 `initialize` 結果的
`serverInfo`、instructions 前 512 字元，`list_tools` 的每個工具 name／title／annotations，
再以 fixture 模式呼叫 `weekly_report(site_url=..., property_id=..., format="markdown")` 印出
前 15 行，以及 `gsc_query(..., site_url=...)` 印出筆數與第一筆。

用法：`uv run --extra google python scripts/smoke_http_client.py --url http://127.0.0.1:8000/mcp`
成功結束碼 0；呼叫失敗時印出錯誤並回非 0。
"""
import argparse
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def _run(url):
    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            server_info = init.serverInfo.model_dump() if hasattr(init.serverInfo, "model_dump") else init.serverInfo
            print("serverInfo：", server_info)
            print("instructions 前 512 字元：")
            print((init.instructions or "")[:512])
            print()

            tools = (await session.list_tools()).tools
            summary = [
                {
                    "name": tool.name,
                    "title": tool.title,
                    "annotations": tool.annotations.model_dump(exclude_none=True) if tool.annotations else None,
                }
                for tool in tools
            ]
            print("list_tools：")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print()

            report = await session.call_tool("weekly_report", {
                "site_url": "sc-domain:example.com",
                "property_id": "123456789",
                "format": "markdown",
            })
            if report.isError:
                raise RuntimeError(f"weekly_report 呼叫失敗：{report.content}")
            markdown = report.structuredContent["result"]
            print('weekly_report(site_url="sc-domain:example.com", property_id="123456789", '
                  'format="markdown") 前 15 行：')
            print("\n".join(markdown.splitlines()[:15]))
            print()

            rows_result = await session.call_tool("gsc_query", {
                "start_date": "2026-10-01",
                "end_date": "2026-10-07",
                "dimensions": ["query"],
                "site_url": "sc-domain:example.com",
            })
            if rows_result.isError:
                raise RuntimeError(f"gsc_query 呼叫失敗：{rows_result.content}")
            rows = rows_result.structuredContent["result"]
            print(f"gsc_query(..., site_url=\"sc-domain:example.com\") 筆數：{len(rows)}")
            print("第一筆：", json.dumps(rows[0], ensure_ascii=False) if rows else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp",
                        help="seo-pulse streamable HTTP 端點，預設 http://127.0.0.1:8000/mcp")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.url))
    except Exception as exc:  # noqa: BLE001 - 驗收腳本，直接印錯誤並以非 0 結束
        print(f"失敗：{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
