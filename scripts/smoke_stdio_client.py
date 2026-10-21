#!/usr/bin/env python3
"""驗收用腳本，不是自動化測試。

依照 `.mcp.json`（Claude／Cursor）與 `.codex-mcp.json`（Codex）裡寫的 command/args 原樣啟動
stdio MCP 伺服器（`${CLAUDE_PLUGIN_ROOT}` 換成這個 repo 的絕對路徑，cwd 固定用 repo 根目錄），
用官方 `mcp` SDK 的 `stdio_client` 連線，印出 `list_tools` 的工具名稱與數量，並以 fixture 模式
（`SEO_PULSE_CONNECTOR=fixture`）呼叫 `weekly_report(format="markdown")`，印出前 15 行。

用法：`uv run --extra google python scripts/smoke_stdio_client.py`
成功結束碼 0；任何一個 manifest 失敗就印出錯誤並回非 0。
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = [".mcp.json", ".codex-mcp.json"]


def _server_params(manifest_name):
    config = json.loads((ROOT / manifest_name).read_text(encoding="utf-8"))
    server = config["mcpServers"]["seo-pulse"]
    args = [arg.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)) for arg in server["args"]]
    env = {**os.environ, "SEO_PULSE_CONNECTOR": "fixture"}
    return StdioServerParameters(command=server["command"], args=args, cwd=str(ROOT), env=env)


async def _run_one(manifest_name):
    print(f"=== {manifest_name} ===")
    params = _server_params(manifest_name)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            names = sorted(tool.name for tool in tools)
            print(f"list_tools：{len(names)} 個工具：{', '.join(names)}")

            result = await session.call_tool("weekly_report", {"format": "markdown"})
            if result.isError:
                raise RuntimeError(f"weekly_report 呼叫失敗：{result.content}")
            markdown = result.structuredContent["result"]
            print('weekly_report(format="markdown") 前 15 行：')
            print("\n".join(markdown.splitlines()[:15]))
    print()


async def main():
    for manifest_name in MANIFESTS:
        await _run_one(manifest_name)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - 驗收腳本，直接印錯誤並以非 0 結束
        print(f"失敗：{exc}", file=sys.stderr)
        sys.exit(1)
