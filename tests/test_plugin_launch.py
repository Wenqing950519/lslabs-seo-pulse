"""Plugin 啟動方式的回歸測試。

Windows 的 PATH 上 `python3` 通常是 Microsoft Store 的空殼，直接用 `python3`
啟動 MCP 伺服器會失敗；plugin 不能自帶 Python 套件，使用者也不該被要求先手動
pip install。manifest 必須改用 uv 以專案為單位啟動，讓 uv 自行建立隔離環境。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP_MANIFESTS = {
    ".mcp.json": "${CLAUDE_PLUGIN_ROOT}",
    ".codex-mcp.json": ".",
}


def _server(path):
    cfg = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return cfg["mcpServers"]["seo-pulse"]


def test_mcp_manifests_launch_with_uv_not_bare_python3():
    for name, project in MCP_MANIFESTS.items():
        server = _server(name)
        assert server["command"] == "uv", f"{name}: 必須用 uv 啟動，不可用裸 python3"
        args = server["args"]
        assert args[:2] == ["run", "--project"], f"{name}: 必須以專案為單位執行"
        assert args[2] == project, f"{name}: --project 指向錯誤"
        assert "--extra" in args and args[args.index("--extra") + 1] == "google", (
            f"{name}: 必須安裝 google 依賴，否則 Google 模式無法啟動"
        )
        assert args[-3:] == ["python", "-m", "seo_pulse_mcp.server"], f"{name}: 入口模組不符"
        assert "python3" not in json.dumps(server), f"{name}: 不得再出現 python3"


def test_uv_lock_committed_and_matches_project_name():
    lock = ROOT / "uv.lock"
    assert lock.exists(), "uv.lock 必須提交，讓 uv run 在使用者機器上可重現"
    assert 'name = "seo-pulse-mcp"' in lock.read_text(encoding="utf-8")
