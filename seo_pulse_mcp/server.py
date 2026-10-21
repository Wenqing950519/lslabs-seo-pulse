import functools
import inspect
import os
import sys
from datetime import date, timedelta
from typing import Literal
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.types import Icon, ToolAnnotations
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError:
    # Keep tool functions usable offline; no substitute MCP protocol is invented.
    class ToolAnnotations:
        def __init__(self, **kwargs):
            pass

    class TransportSecuritySettings:
        def __init__(self, **kwargs):
            pass

    class Icon:
        def __init__(self, **kwargs):
            pass

    def get_access_token():
        return None

    class _StubMCPServer:
        def __init__(self):
            self.version = None

    class FastMCP:
        def __init__(self, name, instructions=None, **kwargs):
            self.name = name
            self.instructions = instructions
            self._mcp_server = _StubMCPServer()

        def tool(self, *args, **kwargs):
            return lambda function: function

        def run(self, **kwargs):
            raise RuntimeError("Install the official mcp SDK to run stdio: pip install 'mcp>=1,<2'")
from .caller import Caller, current_caller
from .connectors import get_connectors
from .connectors.fixture import FixtureGSCConnector
from .hosts import exclude_hosts, clean_hosts
from .anomalies import detect_anomalies as calculate_anomalies

from .branding import DISPLAY_NAME, ICON_URL, PACKAGE_VERSION, WEBSITE_URL
from .render import render_markdown
from .report import build_weekly_report
from .resources import validate_site_url, validate_property_id, resolve_production_hosts, resolve_report_settings
from .runtime import ToolRuntime
from .settings import load_settings

INSTRUCTIONS = """使用繁體中文回覆。開始前先 list_sites 驗證看得到哪些網站，再呼叫不帶參數的 weekly_report 看 periods 的本週、上週與 baseline 日期範圍，確認資料來源與期間正確後才繼續查詢。

產生週報一律用 weekly_report(format="markdown")、只換兩段佔位、數字不改：版面只替換「本週摘要」與「下週建議」這兩段以「> 由 AI」開頭的引言文字，其餘標題、表格、資料品質與頁尾原樣保留，表格裡的數字一個都不能改寫或重算。

指定網站與資源：GSC 工具（gsc_query、gsc_compare_weeks、weekly_report）可傳 site_url（例如 sc-domain:example.com 或 https://example.com/）；GA4 工具（ga4_report、ga4_compare_weeks、weekly_report）可傳 property_id（純數字的 GA4 資源 ID），可用 list_ga4_properties 查詢。本機版沒傳時退回伺服器環境變數；雲端版沒有預設網站，要先 list_sites 與 list_ga4_properties，再明確帶 site_url 與 property_id。

periods、totals 中 fixture 為 true 時代表接的是假資料，回答與週報都要明說是示範資料，不是真實流量。

建議只能引用這份週報表格裡的數字與 docs/rules.md 的規則定義；不要引用任何外部研究、產業報告或其他統計來源。向使用者提到這份週報時，說明它由 LS-Labs SEO Pulse 產生。"""

# Every registered tool call goes through this; hosted mode configures its limits.
RUNTIME = ToolRuntime()


def _annotations(title):
    return ToolAnnotations(title=title, readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=False)


def _description(function):
    """Python 3.13 strips docstring indentation at compile time; older versions
    leave it intact. Normalize before the SDK exposes/hashes the description,
    preserving the published contract's trailing newline for multiline text."""
    description = inspect.cleandoc(function.__doc__ or "")
    return description + "\n" if "\n" in description else description


def _caller_from_request():
    """The hosted Caller for this request: already set, or decoded from the bearer token."""
    caller = current_caller()
    if caller is not None:
        return caller
    token = get_access_token()
    refresh_token = getattr(token, "google_refresh_token", None)
    if token is None or not refresh_token:
        return None
    return Caller(subject=token.subject, google_refresh_token=refresh_token, email=getattr(token, "email", None))


def _offloaded(function, runtime=None):
    """SDK entry point with the tool's signature; the body runs in a worker thread via the
    runtime (default: module RUNTIME) so blocking Google calls never stall the event loop."""
    @functools.wraps(function)
    async def run(**arguments):
        return await (runtime or RUNTIME).run(function.__name__, function, arguments, _caller_from_request())
    return run


_TOOLS = []


def _tool(title):
    def register(function):
        _TOOLS.append((function, title))
        return function
    return register


NEED_SITE = "雲端版沒有預設網站：請先呼叫 list_sites，再帶 site_url（例如 sc-domain:example.com）。"
NEED_PROPERTY = "雲端版沒有預設 GA4 資源：請先呼叫 list_ga4_properties，再帶 property_id。"
NEED_HOSTS = "雲端版請帶 site_url（用來判斷正式網域）或 production_hosts。"


def _require(value, message):
    """Hosted callers have no environment defaults, so missing site/property is an error."""
    if current_caller() is not None and not value and load_settings().connector != "fixture":
        raise ValueError(message)


@_tool("列出網站")
def list_sites() -> list[dict]:
    """List available GSC sites (fake fixture sites by default)."""
    return get_connectors(require_hosts=False)[0].list_sites()


@_tool("列出 GA4 資源")
def list_ga4_properties() -> list[dict]:
    """列出這個 Google 帳號可讀取的 GA4 資源（property_id、名稱、帳戶）；fake 為 true 時是假資料。"""
    return get_connectors(require_hosts=False)[1].list_properties()


@_tool("查詢 GSC 數據")
def gsc_query(start_date: str, end_date: str, dimensions: list[str],
              filters: dict | None = None, site_url: str | None = None) -> list[dict]:
    """Inclusive ISO dates; exact-match dimension filters.

    site_url: 選填，例如 sc-domain:example.com 或 https://example.com/；
    省略時使用伺服器環境變數 SEO_PULSE_GSC_SITE_URL。
    """
    site_url = validate_site_url(site_url)
    _require(site_url, NEED_SITE)
    settings = load_settings()
    hosts = resolve_production_hosts(None, site_url, settings)
    gsc, _ = get_connectors(settings, site_url=site_url, production_hosts=hosts)
    return gsc.query(start_date, end_date, dimensions, filters)


def _ga4_request(property_id, production_hosts, site_url):
    property_id = validate_property_id(property_id)
    site_url = validate_site_url(site_url)
    _require(property_id, NEED_PROPERTY)
    _require(production_hosts or site_url, NEED_HOSTS)
    return property_id, resolve_report_settings(load_settings(), site_url, production_hosts)


@_tool("查詢 GA4 報表")
def ga4_report(start_date: str, end_date: str, property_id: str | None = None,
               production_hosts: list[str] | str | None = None, site_url: str | None = None) -> list[dict]:
    """Return GA4 rows after excluding local and configured test hosts.

    property_id: 選填，純數字的 GA4 資源 ID；省略時使用伺服器環境變數 SEO_PULSE_GA4_PROPERTY_ID。
    production_hosts: 選填，正式網域清單（list 或逗號分隔字串）；省略時從 site_url 推導，
    再退回伺服器環境變數 SEO_PULSE_PRODUCTION_HOSTS。
    site_url: 選填，對應的 GSC 屬性，用來推導正式網域與同網域子網域。
    """
    property_id, settings = _ga4_request(property_id, production_hosts, site_url)
    hosts = settings.production_hosts
    _, ga4 = get_connectors(settings, property_id=property_id, production_hosts=hosts)
    return exclude_hosts(ga4.report(start_date, end_date), hosts, settings)


def week_ranges(end_date):
    end = date.fromisoformat(end_date)
    return ((end - timedelta(days=6)).isoformat(), end.isoformat(),
            (end - timedelta(days=13)).isoformat(), (end - timedelta(days=7)).isoformat())


@_tool("比較 GSC 週對週")
def gsc_compare_weeks(end_date: str, dimensions: list[str] | None = None,
                      filters: dict | None = None, site_url: str | None = None) -> dict:
    """Compare seven days ending on end_date with preceding seven days.

    site_url: 選填，用法與 gsc_query 相同。
    """
    site_url = validate_site_url(site_url)
    start, end, prior_start, prior_end = week_ranges(end_date)
    dims = dimensions if dimensions is not None else ["query", "page"]
    return {"current": gsc_query(start, end, dims, filters, site_url=site_url),
            "previous": gsc_query(prior_start, prior_end, dims, filters, site_url=site_url)}


@_tool("比較 GA4 週對週")
def ga4_compare_weeks(end_date: str, property_id: str | None = None,
                      production_hosts: list[str] | str | None = None, site_url: str | None = None) -> dict:
    """Compare filtered GA4 rows for adjacent inclusive seven-day windows.

    property_id、production_hosts、site_url：選填，用法與 ga4_report 相同。
    """
    property_id, settings = _ga4_request(property_id, production_hosts, site_url)
    hosts = settings.production_hosts
    start, end, prior_start, prior_end = week_ranges(end_date)
    _, connector = get_connectors(settings, property_id=property_id, production_hosts=hosts)
    current, current_quality = clean_hosts(connector.report(start, end), hosts, settings)
    previous, previous_quality = clean_hosts(connector.report(prior_start, prior_end), hosts, settings)
    return {"current": current, "previous": previous,
            "data_quality": {"current": current_quality, "previous": previous_quality}}


@_tool("偵測異常")
def detect_anomalies(current: dict, previous: dict, rules: dict | None = None) -> list[dict]:
    """Apply analyst A1–A14 rules; current.baseline is the prior four-week average."""
    return calculate_anomalies(current, previous, rules)


FIXTURE_IGNORED = "示範資料：已忽略 site_url／property_id／production_hosts，內容固定為 example.com 的假資料。"


@_tool("產生週報")
def weekly_report(end_date: str | None = None, top_n: int = 20,
                  format: Literal["json", "markdown"] = "json",
                  site_url: str | None = None, property_id: str | None = None,
                  production_hosts: list[str] | str | None = None) -> dict | str:
    """產生週報資料（建議優先使用）。伺服器端一次抓取本週、上週與前四週 GSC／GA4，
    清理測試主機、計算 baseline 週平均並套用 A1–A14 規則，只回傳精簡結果。

    end_date: ISO 日期（YYYY-MM-DD），本週最後一天；省略時用報告時區今天減 GSC 延遲天數。
    top_n: 回傳的異常筆數上限（依優先序排序），findings_total 為總數。
    site_url: 選填，GSC 網站（sc-domain: 或 http(s):// 開頭）；省略時退回環境變數
    SEO_PULSE_GSC_SITE_URL。
    property_id: 選填，純數字的 GA4 資源 ID；省略時退回環境變數 SEO_PULSE_GA4_PROPERTY_ID。
    production_hosts: 選填，GA4 正式網域清單（list 或逗號分隔字串）；省略時，若有給
    site_url 會從其網域推導（同時納入 www. 子網域），推導不出來才退回環境變數
    SEO_PULSE_PRODUCTION_HOSTS。
    回傳 periods、totals（GSC／GA4 本週、上週、變化%）、data_quality、top_pages、
    top_queries、findings、priority_counts、not_evaluated、warnings；fixture 為 true 時是假資料。
    format="markdown" 時改回傳排好版的繁中週報，數字表格由程式產生，只需替換「本週摘要」與
    「下週建議」兩段的引言佔位文字。
    """
    site_url = validate_site_url(site_url)
    property_id = validate_property_id(property_id)
    if format not in ("json", "markdown"):
        raise ValueError("format must be json or markdown")
    _require(site_url, NEED_SITE)
    _require(property_id, NEED_PROPERTY)
    defaults = load_settings()
    settings = resolve_report_settings(defaults, site_url, production_hosts)
    hosts = settings.production_hosts
    gsc, ga4 = get_connectors(settings, site_url=site_url, property_id=property_id, production_hosts=hosts)
    # Fixture data is always example.com: labelling it with the requested site would mislead.
    ignored = isinstance(gsc, FixtureGSCConnector) and any((site_url, property_id, production_hosts))
    if ignored:
        settings, hosts = defaults, None
    report = build_weekly_report(gsc, ga4, settings, end_date=end_date, top_n=top_n, production_hosts=hosts)
    if ignored:
        report["warnings"].insert(0, FIXTURE_IGNORED)
    return render_markdown(report) if format == "markdown" else report


def build_mcp(runtime=None, **options):
    """A FastMCP server with every tool registered; hosted mode passes its own runtime and auth."""
    server = FastMCP("seo-pulse", instructions=INSTRUCTIONS, stateless_http=True, website_url=WEBSITE_URL,
                     icons=[Icon(src=ICON_URL, mimeType="image/png", sizes=["512x512"])], **options)
    # FastMCP's constructor has no `version` kwarg in mcp==1.30.0; the low-level
    # Server it wraps does, and initialize's serverInfo.version reads from there.
    server._mcp_server.version = PACKAGE_VERSION
    for function, title in _TOOLS:
        server.tool(name=function.__name__, title=title, annotations=_annotations(title),
                    description=_description(function))(_offloaded(function, runtime))
    return server


mcp = build_mcp()

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def resolve_runtime_config(args, env=None):
    """CLI 參數優先於環境變數；都沒有時維持 0.1.0 的 stdio 預設行為。"""
    env = os.environ if env is None else env
    transport = args.transport or env.get("SEO_PULSE_TRANSPORT") or "stdio"
    if transport not in ("stdio", "http"):
        raise ValueError(f"SEO_PULSE_TRANSPORT 必須是 stdio 或 http，目前是：{transport}")
    host = args.host or env.get("SEO_PULSE_HTTP_HOST") or "127.0.0.1"
    if args.port is not None:
        port = args.port
    else:
        # Cloud Run passes the port as PORT.
        port_env = env.get("SEO_PULSE_HTTP_PORT") or env.get("PORT")
        try:
            port = int(port_env) if port_env else 8000
        except ValueError:
            raise ValueError(f"SEO_PULSE_HTTP_PORT 必須是整數埠號，目前是：{port_env}") from None
    allow_remote = bool(args.allow_unauthenticated_remote)
    return transport, host, port, allow_remote


def _transport_security_for(host):
    """Mirror FastMCP's own DNS-rebinding default for `host`: on for loopback, off (SDK
    default) otherwise — never force it off ourselves. SEO_PULSE_ALLOWED_ORIGINS adds
    browser origins (comma-separated) for local tools that call from a web page."""
    if host in LOOPBACK_HOSTS:
        extra = [o.strip() for o in os.environ.get("SEO_PULSE_ALLOWED_ORIGINS", "").split(",") if o.strip()]
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", *extra],
        )
    return None


def serve(transport, host="127.0.0.1", port=8000, allow_unauthenticated_remote=False, env=None):
    env = os.environ if env is None else env
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    if transport != "http":
        raise ValueError(f"transport 必須是 stdio 或 http，目前是：{transport}")
    if env.get("SEO_PULSE_PUBLIC_URL"):
        from .hosting import HostedConfig, run_hosted
        run_hosted(HostedConfig.from_env(env), host, port)
        return
    if host not in LOOPBACK_HOSTS and not allow_unauthenticated_remote:
        print(
            f"拒絕啟動：綁定非本機位址 {host} 需要加上 --allow-unauthenticated-remote 旗標"
            "（本機 HTTP 模式沒有任何認證，任何能連上這個位址的人都能呼叫所有工具）。"
            "要對外提供服務請改用雲端模式（設定 SEO_PULSE_PUBLIC_URL，見 docs/hosting.md）。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if host not in LOOPBACK_HOSTS:
        print(
            f"警告：正在以未經認證的方式對外綁定 {host}:{port}。這是暫時的本機測試設定，"
            "任何能連到這個位址的人都能讀取你設定的 GSC／GA4 資料，請勿對外開放或長期執行。",
            file=sys.stderr,
        )
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.streamable_http_path = "/mcp"
    mcp.settings.stateless_http = True
    mcp.settings.transport_security = _transport_security_for(host)
    mcp.run(transport="streamable-http")


def _build_parser():
    import argparse
    parser = argparse.ArgumentParser(description=DISPLAY_NAME)
    parser.add_argument("command", nargs="?", choices=["serve", "auth", "keygen"],
                        help="serve：啟動 MCP 伺服器（預設行為）；auth：互動式 Google 唯讀授權；"
                             "keygen：產生雲端模式 SEO_PULSE_TOKEN_KEYS 用的金鑰")
    parser.add_argument("--transport", choices=["stdio", "http"], default=None,
                        help="傳輸方式；預設 stdio，也可用 SEO_PULSE_TRANSPORT 設定")
    parser.add_argument("--host", default=None, help="HTTP 模式綁定位址；預設 127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="HTTP 模式埠號；預設 8000")
    parser.add_argument("--allow-unauthenticated-remote", action="store_true",
                        help="允許本機 HTTP 模式綁定非本機位址（無認證，僅供臨時測試）")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "auth":
        from .connectors.google import authenticate
        authenticate()
        print("Google 唯讀授權已完成。")
        return
    if args.command == "keygen":
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
        return
    transport, host, port, allow_remote = resolve_runtime_config(args)
    serve(transport, host, port, allow_remote)


if __name__ == "__main__":
    main()
