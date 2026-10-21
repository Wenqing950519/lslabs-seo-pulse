"""Resolve per-request site_url / property_id / production_hosts tool parameters.

Priority order: explicit tool parameter > environment variable
(SEO_PULSE_GSC_SITE_URL / SEO_PULSE_GA4_PROPERTY_ID / SEO_PULSE_PRODUCTION_HOSTS).
production_hosts has one extra step before falling back to the environment: if it
is not given but site_url is, the production host(s) are derived from site_url
(see derive_production_hosts). site_url/property_id themselves fall back straight
to the environment inside GoogleGSCConnector/GoogleGA4Connector, unchanged from 0.1.0.
"""
import re
from dataclasses import replace
from urllib.parse import urlparse

from .settings import _host_list


_HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
SITE_URL_ERROR = ("site_url 格式錯誤：必須是 sc-domain: 開頭的網域屬性（例如 sc-domain:example.com），"
                  "或 http(s):// 開頭、含主機名稱的 URL-prefix 屬性（例如 https://example.com/）。")


def _site_host(site_url):
    """Host named by a GSC property, or None when the value names no usable host."""
    if site_url.startswith("sc-domain:"):
        host = site_url[len("sc-domain:"):].strip().lower().rstrip(".")
    elif site_url.startswith(("http://", "https://")):
        host = (urlparse(site_url).hostname or "").lower().rstrip(".")
    else:
        return None
    return host if _HOST.match(host) else None


def validate_site_url(site_url):
    """Raise a Traditional Chinese ValueError if a tool-supplied site_url is malformed.

    An empty `sc-domain:` or a host-less URL is rejected rather than silently
    falling back to the environment default, which would report on another site.
    """
    if site_url is None:
        return None
    if not isinstance(site_url, str) or _site_host(site_url) is None:
        raise ValueError(SITE_URL_ERROR)
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

    `sc-domain:x` 推導出 x 與 www.x：網域屬性常同時涵蓋裸網域與 www，只取一個會把另一邊
    的 GA4 流量誤判為排除。其他子網域不自動納入（見 hosts.clean_hosts 的 subdomain_sessions），
    要納入請明確傳 production_hosts。URL-prefix 屬性只涵蓋單一 origin，所以只取該主機。
    """
    if not site_url:
        return None
    host = _site_host(site_url)
    if not host:
        return None
    if not site_url.startswith("sc-domain:"):
        return (host,)
    apex = host[4:] if host.startswith("www.") else host
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


def resolve_report_settings(settings, site_url=None, production_hosts=None):
    """Keep request-specific hosts and canonical origin together without mutating defaults.

    A domain property does not specify a canonical scheme/subdomain: retain an
    existing canonical origin inside that domain, otherwise default to HTTPS.
    URL-prefix properties supply their own origin (not their path).
    """
    hosts = resolve_production_hosts(production_hosts, site_url, settings)
    origin = settings.canonical_origin
    if site_url:
        if site_url.startswith("sc-domain:"):
            domain = site_url[len("sc-domain:"):].strip().lower().rstrip('.')
            current_host = (urlparse(origin).hostname or '').lower().rstrip('.')
            if domain and not (current_host == domain or current_host.endswith('.' + domain)):
                origin = f"https://{domain}"
        else:
            parsed = urlparse(site_url)
            if parsed.hostname:
                origin = f"{parsed.scheme}://{parsed.netloc}"
    explicit = production_hosts is not None or (derive_production_hosts(site_url) is None and settings.hosts_explicit)
    return replace(settings, production_hosts=hosts, canonical_origin=origin,
                   gsc_site_url=site_url or settings.gsc_site_url, hosts_explicit=explicit)
