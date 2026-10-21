"""Shared display branding."""
import re
from importlib import metadata
from pathlib import Path

DISPLAY_NAME = "LS-Labs SEO Pulse"
WEBSITE_URL = "https://lslabs.tw/seo-pulse/"
ICON_URL = "https://lslabs.tw/brand/logos/ls-labs/ls-labs-app-icon-512.png"


def report_link(edition):
    """Product page link carried in every report footer; UTM tags tell local and cloud apart."""
    return f"{WEBSITE_URL}?utm_source=seo-pulse&utm_medium=report&utm_campaign=weekly-report&utm_content={edition}"


def footer(edition="local"):
    return f"由 [LS-Labs SEO Pulse]({report_link(edition)}) 產生｜MIT"


FOOTER = footer()

_DISTRIBUTION_NAME = "seo-pulse-mcp"
_FALLBACK_VERSION = "0.3.0"


def _read_pyproject_version():
    """Fallback for editable/uninstalled checkouts where metadata lookup fails."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        import tomllib
        return tomllib.loads(text)["project"]["version"]
    except ModuleNotFoundError:
        pass
    project = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)", text)
    match = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', project.group(1)) if project else None
    return match.group(1) if match else None


def package_version():
    """Installed distribution version (`pip install`/`uv sync` records this), falling
    back to pyproject.toml and finally a fixed string for a bare checkout."""
    try:
        return metadata.version(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return _read_pyproject_version() or _FALLBACK_VERSION


PACKAGE_VERSION = package_version()
