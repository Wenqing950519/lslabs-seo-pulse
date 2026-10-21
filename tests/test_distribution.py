"""The ChatGPT/Codex submission package must match the package and the hosted server."""
import importlib.util
import json
from pathlib import Path

from seo_pulse_mcp.auth import SCOPE
from seo_pulse_mcp.branding import WEBSITE_URL

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "distribution" / "openai"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_openai_plugin", ROOT / "scripts" / "build_openai_plugin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_matches_package_and_site():
    builder = _load_builder()
    manifest = json.loads((SOURCE / "plugin.json").read_text(encoding="utf-8"))
    assert builder.check(manifest, builder.read_project_version()) == []
    interface = manifest["extensions"]["com.openai"]["interface"]
    assert interface["websiteURL"] == WEBSITE_URL
    assert interface["privacyPolicyURL"] == WEBSITE_URL + "privacy/"
    assert interface["termsOfServiceURL"] == WEBSITE_URL + "terms/"
    assert "MCP" not in interface["displayName"] and "Plugin" not in interface["displayName"]


def test_remote_server_uses_oauth_dcr_without_secrets():
    server = json.loads((SOURCE / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["seo-pulse"]
    assert server["type"] == "streamable-http" and server["url"].startswith("https://") and server["url"].endswith("/mcp")
    auth = server["extensions"]["com.openai"]["auth"]
    assert auth == {"type": "oauth", "client": {"mode": "dcr"}, "baseScopes": [SCOPE]}
    assert "headers" not in server


def test_zip_contains_manifest_skill_and_icon(tmp_path):
    import zipfile
    builder = _load_builder()
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"\x89PNG\r\n\x1a\n")
    target = builder.build(icon, tmp_path / "dist")
    with zipfile.ZipFile(target) as archive:
        assert sorted(archive.namelist()) == ["assets/icon.png", "mcp.json", "plugin.json", "skills/seo-pulse/SKILL.md"]
