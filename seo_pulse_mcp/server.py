from datetime import date, timedelta
from typing import Literal
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Keep tool functions usable offline; no substitute MCP protocol is invented.
    class FastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self):
            return lambda function: function

        def run(self, **kwargs):
            raise RuntimeError("Install the official mcp SDK to run stdio: pip install 'mcp>=1,<2'")
from .connectors import get_connectors
from .hosts import exclude_hosts, clean_hosts
from .anomalies import detect_anomalies as calculate_anomalies

from .branding import DISPLAY_NAME
from .render import render_markdown
from .report import build_weekly_report
from .settings import load_settings

mcp = FastMCP("seo-pulse")


@mcp.tool()
def list_sites() -> list[dict]:
    """List available GSC sites (fake fixture sites by default)."""
    return get_connectors()[0].list_sites()


@mcp.tool()
def gsc_query(start_date: str, end_date: str, dimensions: list[str],
              filters: dict | None = None) -> list[dict]:
    """Inclusive ISO dates; exact-match dimension filters."""
    return get_connectors()[0].query(start_date, end_date, dimensions, filters)


@mcp.tool()
def ga4_report(start_date: str, end_date: str) -> list[dict]:
    """Return GA4 rows after excluding local and configured test hosts."""
    return exclude_hosts(get_connectors()[1].report(start_date, end_date))


def week_ranges(end_date):
    end = date.fromisoformat(end_date)
    return ((end - timedelta(days=6)).isoformat(), end.isoformat(),
            (end - timedelta(days=13)).isoformat(), (end - timedelta(days=7)).isoformat())


@mcp.tool()
def gsc_compare_weeks(end_date: str, dimensions: list[str] | None = None,
                      filters: dict | None = None) -> dict:
    """Compare seven days ending on end_date with preceding seven days."""
    start, end, prior_start, prior_end = week_ranges(end_date)
    dims = dimensions if dimensions is not None else ["query", "page"]
    return {"current": gsc_query(start, end, dims, filters),
            "previous": gsc_query(prior_start, prior_end, dims, filters)}


@mcp.tool()
def ga4_compare_weeks(end_date: str) -> dict:
    """Compare filtered GA4 rows for adjacent inclusive seven-day windows."""
    start, end, prior_start, prior_end = week_ranges(end_date)
    connector = get_connectors()[1]
    current, current_quality = clean_hosts(connector.report(start, end))
    previous, previous_quality = clean_hosts(connector.report(prior_start, prior_end))
    return {"current": current, "previous": previous,
            "data_quality": {"current": current_quality, "previous": previous_quality}}


@mcp.tool()
def detect_anomalies(current: dict, previous: dict, rules: dict | None = None) -> list[dict]:
    """Apply analyst A1–A14 rules; current.baseline is the prior four-week average."""
    return calculate_anomalies(current, previous, rules)


@mcp.tool()
def weekly_report(end_date: str | None = None, top_n: int = 20,
                  format: Literal["json", "markdown"] = "json") -> dict | str:
    """產生週報資料（建議優先使用）。伺服器端一次抓取本週、上週與前四週 GSC／GA4，
    清理測試主機、計算 baseline 週平均並套用 A1–A14 規則，只回傳精簡結果。

    end_date: ISO 日期（YYYY-MM-DD），本週最後一天；省略時用報告時區今天減 GSC 延遲天數。
    top_n: 回傳的異常筆數上限（依優先序排序），findings_total 為總數。
    回傳 periods、totals（GSC／GA4 本週、上週、變化%）、data_quality、top_pages、
    top_queries、findings、priority_counts、not_evaluated、warnings；fixture 為 true 時是假資料。
    format="markdown" 時改回傳排好版的繁中週報，數字表格由程式產生，只需替換「本週摘要」與
    「下週建議」兩段的引言佔位文字。
    """
    settings = load_settings()
    gsc, ga4 = get_connectors(settings)
    if format not in ("json", "markdown"):
        raise ValueError("format must be json or markdown")
    report = build_weekly_report(gsc, ga4, settings, end_date=end_date, top_n=top_n)
    return render_markdown(report) if format == "markdown" else report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=DISPLAY_NAME)
    parser.add_argument("command", nargs="?", choices=["auth"])
    args = parser.parse_args()
    if args.command == "auth":
        from .connectors.google import authenticate
        authenticate()
        print("Google 唯讀授權已完成。")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
