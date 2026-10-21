import copy
import importlib.util
import json
from pathlib import Path

import pytest

import mcp  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = [
    ROOT / ".claude-plugin" / "plugin.json",
    ROOT / ".codex-plugin" / "plugin.json",
    ROOT / ".cursor-plugin" / "plugin.json",
]

REMINDER = (
    "提醒：任何工具名稱、描述或 schema 的改動，都必須提高版本號"
    "（pyproject.toml 與 .claude-plugin/.codex-plugin/.cursor-plugin 的 plugin.json），"
    "並重新執行 `python scripts/generate_tool_contract.py`。\n"
    "Reminder: any change to a tool name, description or schema requires bumping the "
    "version (pyproject.toml + the three plugin.json files) and re-running "
    "`python scripts/generate_tool_contract.py`."
)


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "generate_tool_contract", ROOT / "scripts" / "generate_tool_contract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_script()


def _committed():
    return json.loads((ROOT / "tool-contract.json").read_text(encoding="utf-8"))


def test_live_contract_matches_committed():
    live = gen.build_contract()
    committed = _committed()
    if live != committed:
        lines = gen.diff_contracts(committed, live)
        pytest.fail("tool-contract.json 與伺服器不一致:\n" + "\n".join(lines) + "\n" + REMINDER)


def test_stored_hashes_are_self_consistent():
    contract = _committed()
    assert contract["contract_format"] == 2
    for tool in contract["tools"]:
        digests = tool["sha256"]
        assert digests["description"] == gen.sha(tool["description"]), tool["name"]
        assert digests["input_schema"] == gen.sha(tool["input_schema"]), tool["name"]
        assert digests["annotations"] == gen.sha(tool["annotations"]), tool["name"]
        assert digests["tool"] == gen.sha(
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
                "title": tool["title"],
                "annotations": tool["annotations"],
            }
        ), tool["name"]
        expected_hints = {"readOnlyHint": True, "destructiveHint": False,
                          "idempotentHint": True, "openWorldHint": False}
        for hint, value in expected_hints.items():
            assert tool["annotations"][hint] is value, tool["name"]
        assert tool["title"]
    assert contract["fingerprint"] == gen.sha([t["sha256"]["tool"] for t in contract["tools"]])
    names = [t["name"] for t in contract["tools"]]
    assert names == sorted(names)


def test_versions_are_consistent():
    py_version = gen.read_project_version()
    assert _committed()["version"] == py_version
    for path in MANIFESTS:
        version = json.loads(path.read_text(encoding="utf-8"))["version"]
        assert version == py_version, path.name


def test_plugin_manifests_sanity():
    for path in [*MANIFESTS, ROOT / ".claude-plugin" / "marketplace.json", ROOT / ".mcp.json"]:
        json.loads(path.read_text(encoding="utf-8"))

    mcp_cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp_cfg["mcpServers"]["seo-pulse"]["args"][-3:] == ["python", "-m", "seo_pulse_mcp.server"]

    for path in MANIFESTS:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for key in ("skills", "mcpServers"):
            if key in manifest:
                assert (ROOT / manifest[key]).exists(), f"{path.parent.name}: {key}"

    skill = (ROOT / "skills" / "seo-pulse" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\n")
    frontmatter = skill.split("---", 2)[1]
    assert "name: seo-pulse" in frontmatter.splitlines()


def test_diff_contracts_reports_changed_description():
    committed = _committed()
    altered = copy.deepcopy(committed)
    altered["tools"][0]["description"] += " (changed)"
    name = altered["tools"][0]["name"]
    lines = gen.diff_contracts(committed, altered)
    assert any(name in line and "description" in line for line in lines)
    assert gen.diff_contracts(committed, committed) == []


def test_diff_contracts_reports_changed_annotation():
    """A8: tampering with a single annotation must be detected, not silently accepted."""
    committed = _committed()
    altered = copy.deepcopy(committed)
    altered["tools"][0]["annotations"]["readOnlyHint"] = False
    name = altered["tools"][0]["name"]
    lines = gen.diff_contracts(committed, altered)
    assert any(name in line and "annotation" in line.lower() for line in lines)
    assert gen.sha(altered["tools"][0]["annotations"]) != committed["tools"][0]["sha256"]["annotations"]
