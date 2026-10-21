"""Resolve per-request site_url / property_id / production_hosts tool parameters.

Priority order: explicit tool parameter > environment variable
(SEO_PULSE_GSC_SITE_URL / SEO_PULSE_GA4_PROPERTY_ID / SEO_PULSE_PRODUCTION_HOSTS).
production_hosts has one extra step before falling back to the environment: if it
is not given but site_url is, the production host(s) are derived from site_url
(see derive_production_hosts). site_url/property_id themselves fall back straight
to the environment inside GoogleGSCConnector/GoogleGA4Connector, unchanged from 0.1.0.
"""
from urllib.parse import urlparse

from .settings import _host_list


def validate_site_url(site_url):
    """Raise a Traditional Chinese ValueError if a tool-supplied site_url is malformed."""
    if site_url is None:
        return None
    if not (site_url.startswith("sc-domain:") or site_url.startswith("http://")
            or site_url.startswith("https://")):
        raise ValueError(
            "site_url 格式錯誤：必須是 sc-domain: 開頭的網域屬性，"
            "或 http(s):// 開頭的 URL-prefix 屬性。"
        )
    return site_url


def validate_property_id(property_id):
    """Raise a Traditional Chinese ValueError if a tool-supplied property_id is malformed."""
    if property_id is None:
        return None
    text = str(property_id).strip()
    if not text.isdigit():
        raise ValueError(
            "property_id 格式錯誤：必須是純數字的 GA4 資源 ID（例如 123456789），"
            "不是 G- 開頭的評估 ID。"
        )
    return text


def derive_production_hosts(site_url):
    """Derive GA4 production host(s) from a GSC site_url, or None when not derivable.

    `sc-domain:x` 或 `http(s)://x/` 推導出 x；同時納入 x 與 www.x 兩者，因為同一個網域
    屬性常同時涵蓋裸網域與 www 子網域，只納入其中一個會讓另一邊的 GA4 流量被誤判為污染。
    """
    if not site_url:
        return None
    host = None
    if site_url.startswith("sc-domain:"):
        host = site_url[len("sc-domain:"):].strip().lower()
    elif site_url.startswith("http://") or site_url.startswith("https://"):
        host = (urlparse(site_url).hostname or "").lower()
    if not host:
        return None
    apex = host[4:] if host.startswith("www.") else host
    if not apex:
        return None
    return tuple(sorted({apex, f"www.{apex}"}))


def normalize_production_hosts(value):
    """Accept list[str] or a comma string; normalize the same way as settings._host_list."""
    if value is None:
        return None
    text = value if isinstance(value, str) else ",".join(value)
    return _host_list(text)


def resolve_production_hosts(production_hosts, site_url, settings):
    """tool param > derived from tool-supplied site_url > settings (env var or default)."""
    if production_hosts is not None:
        return normalize_production_hosts(production_hosts)
    derived = derive_production_hosts(site_url)
    if derived is not None:
        return derived
    return settings.production_hosts
