"""Audit 2026-10-21 §3.B: parameter-path defects found in PR #2.

- Domain properties cover every subdomain, so sibling subdomains of the GSC
  domain are reported separately instead of being counted as pollution.
- URL-prefix properties cover one origin, so only that host is derived.
- Empty or host-less site_url values are rejected instead of silently falling
  back to the environment default.
- A malformed SEO_PULSE_HTTP_PORT gives a Traditional Chinese error.
- Fixture mode ignores site_url/property_id and says so.
"""
from types import SimpleNamespace as NS

import pytest

from seo_pulse_mcp import server
from seo_pulse_mcp.hosts import clean_hosts
from seo_pulse_mcp.resources import derive_production_hosts, resolve_report_settings, validate_site_url
from seo_pulse_mcp.settings import load_settings


def _rows():
    return [dict(hostName="example.com", sessions=60),
            dict(hostName="www.example.com", sessions=20),
            dict(hostName="blog.example.com", sessions=100),
            dict(hostName="localhost", sessions=20)]


def test_domain_property_siblings_are_not_pollution():
    settings = resolve_report_settings(load_settings({}), "sc-domain:example.com")
    kept, quality = clean_hosts(_rows(), settings.production_hosts, settings)
    assert {r["hostName"] for r in kept} == {"example.com", "www.example.com"}
    assert quality["excluded_sessions"] == 120
    assert quality["subdomain_sessions"] == 100
    assert quality["subdomain_hosts"] == ["blog.example.com"]
    assert quality["pollution_ratio"] == pytest.approx(20 / 200)
    assert not quality["pollution_warning"]


def test_env_site_url_enables_sibling_split_for_local_reports():
    settings = load_settings({"SEO_PULSE_GSC_SITE_URL": "sc-domain:lslabs.tw",
                              "SEO_PULSE_PRODUCTION_HOSTS": "lslabs.tw"})
    rows = [dict(hostName="lslabs.tw", sessions=50), dict(hostName="geocheck.lslabs.tw", sessions=40),
            dict(hostName="ls-labs.pages.dev", sessions=10)]
    kept, quality = clean_hosts(rows, settings=settings)
    assert [r["hostName"] for r in kept] == ["lslabs.tw"]
    assert quality["subdomain_sessions"] == 40
    assert quality["pollution_ratio"] == pytest.approx(0.1)


def test_url_prefix_property_has_no_sibling_split():
    settings = resolve_report_settings(load_settings({}), "https://example.com/")
    _, quality = clean_hosts(_rows(), settings.production_hosts, settings)
    assert quality["subdomain_sessions"] == 0
    assert quality["pollution_ratio"] == quality["excluded_ratio"]


@pytest.mark.parametrize("site_url, expected", [
    ("sc-domain:example.com", ("example.com", "www.example.com")),
    ("sc-domain:www.example.com", ("example.com", "www.example.com")),
    ("https://blog.example.com/", ("blog.example.com",)),
    ("https://www.example.com/", ("www.example.com",)),
    ("http://example.com:8080/path/", ("example.com",)),
])
def test_derivation_follows_property_type(site_url, expected):
    assert derive_production_hosts(site_url) == expected


@pytest.mark.parametrize("site_url", ["sc-domain:", "sc-domain:  ", "https://", "http:///path",
                                      "sc-domain:https://example.com", "sc-domain:exa mple.com"])
def test_hostless_site_url_is_rejected(site_url):
    with pytest.raises(ValueError, match="site_url"):
        validate_site_url(site_url)


def test_bad_port_env_has_readable_error():
    args = NS(transport="http", host=None, port=None, allow_unauthenticated_remote=False)
    with pytest.raises(ValueError, match="SEO_PULSE_HTTP_PORT"):
        server.resolve_runtime_config(args, env={"SEO_PULSE_HTTP_PORT": "abc"})


def test_fixture_report_ignores_site_url_and_says_so(monkeypatch):
    monkeypatch.setenv("SEO_PULSE_CONNECTOR", "fixture")
    report = server.weekly_report(site_url="sc-domain:customer.example", property_id="123")
    assert report["fixture"]
    assert report["site"] == "https://example.com"
    assert any("site_url" in w and "示範" in w for w in report["warnings"])


def _report(env, **kwargs):
    from unittest.mock import Mock
    from seo_pulse_mcp.report import build_weekly_report
    gsc, ga4 = Mock(), Mock()
    gsc.query.return_value = []
    ga4.report.return_value = [dict(date="2026-10-18", hostName="example.com", sessions=10),
                               dict(date="2026-10-18", hostName="blog.example.com", sessions=5)]
    settings = resolve_report_settings(load_settings(env), **kwargs)
    return build_weekly_report(gsc, ga4, settings, end_date="2026-10-18",
                               production_hosts=settings.production_hosts)


def test_subdomain_hint_only_when_hosts_were_derived():
    derived = _report({}, site_url="sc-domain:example.com")
    assert any("production_hosts" in w for w in derived["warnings"])
    chosen_env = _report({"SEO_PULSE_GSC_SITE_URL": "sc-domain:example.com",
                          "SEO_PULSE_PRODUCTION_HOSTS": "example.com"})
    chosen_param = _report({}, site_url="sc-domain:example.com", production_hosts="example.com")
    for report in (chosen_env, chosen_param):
        assert not any("production_hosts" in w for w in report["warnings"])
        assert report["data_quality"]["current"]["subdomain_sessions"] == 5
