"""Cross-site reports must agree on totals, anomalies and site identity."""
from unittest.mock import Mock

import pytest

from seo_pulse_mcp import server
from seo_pulse_mcp.report import build_weekly_report
from seo_pulse_mcp.resources import resolve_report_settings
from seo_pulse_mcp.settings import load_settings


def connectors(host):
    gsc, ga4 = Mock(), Mock()
    gsc.query.side_effect = lambda start, end, dimensions: [dict(
        date=end, query="搜尋", page=f"https://{host}/article", clicks=100,
        impressions=1000, position=1)]

    def rows(start, end):
        current = end == "2026-10-18"
        return [dict(date=end, hostName=host, sessions=10 if current else 100,
                     keyEvents=1 if current else 10,
                     sessionDefaultChannelGroup="Organic Search", sessionSource="google"),
                dict(date=end, hostName="localhost", sessions=50, keyEvents=0,
                     sessionDefaultChannelGroup="Direct", sessionSource="(direct)")]

    ga4.report.side_effect = rows
    return gsc, ga4


def test_builder_host_override_preserves_drop_findings_and_raw_quality():
    defaults = load_settings({"SEO_PULSE_PRODUCTION_HOSTS": "old.example"})
    report = build_weekly_report(*connectors("new.example"), defaults,
                                 end_date="2026-10-18", production_hosts=("new.example",))
    assert report["totals"]["ga4"]["current"]["sessions"] == 10
    assert report["totals"]["ga4"]["previous"]["sessions"] == 100
    findings = {f["rule"]: f for f in report["findings"]}
    assert findings["A10"]["current"] == 10
    assert findings["A10"]["previous"] == 100
    assert findings["A11"]["current"] == 1
    assert findings["A11"]["previous"] == 10
    assert report["data_quality"]["current"]["excluded_sessions"] == 50
    assert report["data_quality"]["current"]["excluded_ratio"] == pytest.approx(50 / 60)
    assert defaults.production_hosts == ("old.example",)


def test_weekly_tool_switches_site_without_leaking_into_next_request(monkeypatch):
    monkeypatch.setenv("SEO_PULSE_PRODUCTION_HOSTS", "old.example")
    monkeypatch.setenv("SEO_PULSE_CANONICAL_ORIGIN", "https://old.example")

    def get_connectors(settings=None, **kwargs):
        host = "new.example" if kwargs.get("site_url") else "old.example"
        return connectors(host)

    monkeypatch.setattr(server, "get_connectors", get_connectors)
    report = server.weekly_report("2026-10-18", site_url="sc-domain:new.example", property_id="123")
    assert report["site"] == "https://new.example"
    rules = {f["rule"] for f in report["findings"]}
    assert {"A10", "A11"} <= rules
    assert "A9" not in rules
    markdown = server.weekly_report("2026-10-18", site_url="sc-domain:new.example", format="markdown")
    assert "https://new.example" in markdown
    assert "old.example" not in markdown
    default_report = server.weekly_report("2026-10-18")
    assert default_report["site"] == "https://old.example"
    assert "A9" not in {f["rule"] for f in default_report["findings"]}


@pytest.mark.parametrize("site_url,expected", [
    ("sc-domain:new.example", "https://new.example"),
    ("http://www.new.example:8080/blog/", "http://www.new.example:8080"),
    ("sc-domain:old.example", "https://www.old.example"),
    ("sc-domain:example", "https://www.old.example"),
    (None, "https://www.old.example"),
])
def test_request_origin_resolution_preserves_defaults_and_url_prefix(site_url, expected):
    defaults = load_settings({"SEO_PULSE_PRODUCTION_HOSTS": "old.example",
                              "SEO_PULSE_CANONICAL_ORIGIN": "https://www.old.example"})
    resolved = resolve_report_settings(defaults, site_url, ["chosen.example"])
    assert resolved.canonical_origin == expected
    assert resolved.production_hosts == ("chosen.example",)
    assert defaults.canonical_origin == "https://www.old.example"
    assert defaults.production_hosts == ("old.example",)


def test_unrelated_domain_suffix_does_not_reuse_old_canonical_origin():
    defaults = load_settings({"SEO_PULSE_CANONICAL_ORIGIN": "https://notexample.com"})
    assert resolve_report_settings(defaults, "sc-domain:example.com").canonical_origin == "https://example.com"


def test_tool_descriptions_are_stable_across_python_docstring_formats(monkeypatch):
    registered = []

    def tool(**kwargs):
        registered.append(kwargs["description"])
        return lambda function: function

    monkeypatch.setattr(server.mcp, "tool", tool)
    for doc in ["Summary.\n\n    Details.\n    ", "Summary.\n\nDetails.\n"]:
        def example():
            pass
        example.__doc__ = doc
        server._tool("Example")(example)
    assert registered == ["Summary.\n\nDetails.\n"] * 2
