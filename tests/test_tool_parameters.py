"""A4/A5: site_url / property_id / production_hosts resolve from tool parameters,
not just environment variables, with the tool parameter always winning.

get_connectors is monkeypatched so these tests never construct a real Google
connector or touch the network; they only assert what server.py resolves and
passes down.
"""
from unittest.mock import Mock

import pytest

from seo_pulse_mcp import server


def _fake_connectors(monkeypatch):
    calls = []
    gsc, ga4 = Mock(), Mock()
    gsc.query.return_value = []
    ga4.report.return_value = []

    def fake_get_connectors(settings=None, *, site_url=None, property_id=None, production_hosts=None):
        calls.append({"site_url": site_url, "property_id": property_id, "production_hosts": production_hosts})
        return gsc, ga4

    monkeypatch.setattr(server, "get_connectors", fake_get_connectors)
    return calls, gsc, ga4


# --- A4: tool parameter reaches the connector, not the environment value --------

def test_gsc_query_uses_tool_site_url_not_env(monkeypatch):
    calls, gsc, _ = _fake_connectors(monkeypatch)
    monkeypatch.setenv("SEO_PULSE_GSC_SITE_URL", "sc-domain:env-example.com")
    server.gsc_query("2026-01-01", "2026-01-02", ["query"], site_url="sc-domain:tool-example.com")
    assert calls[-1]["site_url"] == "sc-domain:tool-example.com"


def test_ga4_report_uses_tool_property_id_not_env(monkeypatch):
    calls, _, ga4 = _fake_connectors(monkeypatch)
    monkeypatch.setenv("SEO_PULSE_GA4_PROPERTY_ID", "999999999")
    server.ga4_report("2026-01-01", "2026-01-02", property_id="123456789")
    assert calls[-1]["property_id"] == "123456789"


def test_ga4_compare_weeks_uses_tool_property_id_not_env(monkeypatch):
    calls, _, ga4 = _fake_connectors(monkeypatch)
    monkeypatch.setenv("SEO_PULSE_GA4_PROPERTY_ID", "999999999")
    server.ga4_compare_weeks("2026-10-11", property_id="123456789")
    assert calls[-1]["property_id"] == "123456789"


def test_weekly_report_uses_tool_params_not_env(monkeypatch):
    calls, gsc, ga4 = _fake_connectors(monkeypatch)
    monkeypatch.setenv("SEO_PULSE_GSC_SITE_URL", "sc-domain:env-example.com")
    monkeypatch.setenv("SEO_PULSE_GA4_PROPERTY_ID", "999999999")
    monkeypatch.setenv("SEO_PULSE_PRODUCTION_HOSTS", "env-example.com")
    server.weekly_report(site_url="sc-domain:tool-example.com", property_id="123456789",
                         production_hosts="tool-example.com")
    assert calls[-1]["site_url"] == "sc-domain:tool-example.com"
    assert calls[-1]["property_id"] == "123456789"
    assert calls[-1]["production_hosts"] == ("tool-example.com",)


# --- A5: environment-only behaviour matches 0.1.0; tool param wins when both set --

def test_production_hosts_env_only_falls_back_like_0_1_0(monkeypatch):
    calls, _, _ = _fake_connectors(monkeypatch)
    monkeypatch.setenv("SEO_PULSE_PRODUCTION_HOSTS", "legacy.tw")
    server.ga4_report("2026-01-01", "2026-01-02")
    assert calls[-1]["production_hosts"] == ("legacy.tw",)


def test_production_hosts_tool_param_wins_over_env(monkeypatch):
    calls, _, _ = _fake_connectors(monkeypatch)
    monkeypatch.setenv("SEO_PULSE_PRODUCTION_HOSTS", "legacy.tw")
    server.ga4_report("2026-01-01", "2026-01-02", production_hosts="tool.tw")
    assert calls[-1]["production_hosts"] == ("tool.tw",)


def test_weekly_report_derives_production_hosts_from_tool_site_url(monkeypatch):
    calls, gsc, ga4 = _fake_connectors(monkeypatch)
    monkeypatch.setenv("SEO_PULSE_PRODUCTION_HOSTS", "should-not-be-used.tw")
    server.weekly_report(site_url="sc-domain:example.org")
    assert calls[-1]["production_hosts"] == ("example.org", "www.example.org")


def test_gsc_query_with_no_params_and_no_env_matches_0_1_0(monkeypatch):
    calls, gsc, _ = _fake_connectors(monkeypatch)
    server.gsc_query("2026-01-01", "2026-01-02", ["query"])
    assert calls[-1]["site_url"] is None


# --- tool-parameter format validation --------------------------------------------

def test_gsc_query_rejects_malformed_site_url(monkeypatch):
    _fake_connectors(monkeypatch)
    with pytest.raises(ValueError, match="site_url"):
        server.gsc_query("2026-01-01", "2026-01-02", ["query"], site_url="example.com")


def test_ga4_report_rejects_non_numeric_property_id(monkeypatch):
    _fake_connectors(monkeypatch)
    with pytest.raises(ValueError, match="property_id"):
        server.ga4_report("2026-01-01", "2026-01-02", property_id="G-ABC123")


# --- get_connectors' default-hosts guard must use the resolved production_hosts,
# not just the environment variable, when site_url is supplied (spec 2.3) -------

def test_gsc_query_google_mode_not_blocked_when_site_url_resolves_hosts(monkeypatch):
    import seo_pulse_mcp.connectors.google as g
    monkeypatch.setenv("SEO_PULSE_CONNECTOR", "google")
    monkeypatch.delenv("SEO_PULSE_PRODUCTION_HOSTS", raising=False)
    fake_gsc = Mock()
    fake_gsc.query.return_value = []
    fake_gsc_cls = Mock(return_value=fake_gsc)
    monkeypatch.setattr(g, "GoogleGSCConnector", fake_gsc_cls)
    monkeypatch.setattr(g, "GoogleGA4Connector", Mock(return_value=Mock()))

    server.gsc_query("2026-01-01", "2026-01-02", ["query"], site_url="sc-domain:lslabs.tw")

    assert fake_gsc_cls.call_args.kwargs["site_url"] == "sc-domain:lslabs.tw"


def test_gsc_query_google_mode_still_blocked_without_site_url(monkeypatch):
    import seo_pulse_mcp.connectors.google as g
    monkeypatch.setenv("SEO_PULSE_CONNECTOR", "google")
    monkeypatch.delenv("SEO_PULSE_PRODUCTION_HOSTS", raising=False)
    monkeypatch.setattr(g, "GoogleGSCConnector", Mock())
    monkeypatch.setattr(g, "GoogleGA4Connector", Mock())

    with pytest.raises(ValueError, match="SEO_PULSE_PRODUCTION_HOSTS"):
        server.gsc_query("2026-01-01", "2026-01-02", ["query"])
