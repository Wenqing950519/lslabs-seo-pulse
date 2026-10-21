#!/usr/bin/env python3
"""Package the ChatGPT/Codex plugin directory submission ZIP (remote MCP + Skill).

The ZIP holds distribution/openai/{plugin.json,mcp.json}, the canonical
skills/seo-pulse/SKILL.md and the official LS-Labs app icon from the sibling
home repo (not copied into this repo). No secrets: the hosted server registers
ChatGPT through dynamic client registration.

Usage: uv run python scripts/build_openai_plugin.py [--icon PATH] [--out dist/]
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "distribution" / "openai"
DEFAULT_ICON = ROOT.parent / "home" / "brand" / "logos" / "ls-labs" / "ls-labs-app-icon-512.png"


def read_project_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return next(line.split('"')[1] for line in text.splitlines() if line.startswith("version = "))


def check(manifest, version):
    """Fail on drift between the submission manifest and the package."""
    problems = []
    if manifest["version"] != version:
        problems.append(f"distribution/openai/plugin.json 版本 {manifest['version']} 與 pyproject {version} 不一致")
    interface = manifest["extensions"]["com.openai"]["interface"]
    if len(interface["displayName"]) > 30:
        problems.append("displayName 超過 30 字")
    for key in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        if not interface[key].startswith("https://"):
            problems.append(f"{key} 必須是 HTTPS")
    return problems


def build(icon, out_dir):
    manifest = json.loads((SOURCE / "plugin.json").read_text(encoding="utf-8"))
    problems = check(manifest, read_project_version())
    if not icon.is_file():
        problems.append(f"找不到圖示 {icon}（預設取相鄰 home repo 的官方 app icon，可用 --icon 指定）")
    if problems:
        raise SystemExit("\n".join(problems))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"seo-pulse-openai-{manifest['version']}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(SOURCE / "plugin.json", "plugin.json")
        archive.write(SOURCE / "mcp.json", "mcp.json")
        archive.write(ROOT / "skills" / "seo-pulse" / "SKILL.md", "skills/seo-pulse/SKILL.md")
        archive.write(icon, "assets/icon.png")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icon", type=Path, default=DEFAULT_ICON)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build(args.icon, args.out), file=sys.stdout)


if __name__ == "__main__":
    main()
