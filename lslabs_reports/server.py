from datetime import date, timedelta
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

mcp = FastMCP("LS-Labs Reports")


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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
