from datetime import datetime, timezone

import pytest

from seo_pulse_mcp import server
from seo_pulse_mcp.connectors import get_connectors
from seo_pulse_mcp.report import build_weekly_report
from seo_pulse_mcp.settings import load_settings


class FakeGSC:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def list_sites(self):
        return []

    def query(self, start_date, end_date, dimensions, filters=None):
        self.calls.append((start_date, end_date, list(dimensions)))
        rows = [r for r in self.rows if start_date <= r['date'] <= end_date]
        return [{k: r[k] for k in [*dimensions, 'clicks', 'impressions', 'position']} for r in rows]


class FakeGA4:
    def __init__(self, rows):
        self.rows = rows

    def report(self, start_date, end_date):
        return [dict(r) for r in self.rows if start_date <= r['date'] <= end_date]


def gsc_row(day, clicks=10, impressions=100, position=5, query='查詢', page='https://example.com/'):
    return dict(date=day, query=query, page=page, clicks=clicks, impressions=impressions, position=position)


def settings(**env):
    return load_settings({'SEO_PULSE_PRODUCTION_HOSTS': 'example.com', **env})


# --- settings ---------------------------------------------------------------

def test_settings_defaults_and_parsing():
    s = load_settings({'SEO_PULSE_PRODUCTION_HOSTS': 'LSLabs.tw., www.lslabs.tw',
                       'SEO_PULSE_EXCLUDE_HOSTS': ' staging.lslabs.tw ,',
                       'SEO_PULSE_GSC_LAG_DAYS': '2'})
    assert s.connector == 'fixture'
    assert s.production_hosts == ('lslabs.tw', 'www.lslabs.tw')
    assert s.exclude_hosts == ('staging.lslabs.tw',)
    assert s.canonical_origin == 'https://lslabs.tw'
    assert s.timezone == 'Asia/Taipei' and s.gsc_lag_days == 2


def test_settings_reject_bad_values():
    with pytest.raises(ValueError, match='SEO_PULSE_CONNECTOR'):
        load_settings({'SEO_PULSE_CONNECTOR': 'other'})
    with pytest.raises(ValueError, match='SEO_PULSE_GSC_LAG_DAYS'):
        load_settings({'SEO_PULSE_GSC_LAG_DAYS': 'three'})
    with pytest.raises(ValueError, match='SEO_PULSE_TIMEZONE'):
        load_settings({'SEO_PULSE_TIMEZONE': 'Mars/Base'})


def test_default_end_date_uses_taipei_today_minus_lag():
    # 2026-10-16 17:00 UTC is already 2026-10-17 in Taipei; minus 3 days of GSC lag.
    now = datetime(2026, 10, 16, 17, tzinfo=timezone.utc)
    assert settings().default_end_date(now).isoformat() == '2026-10-14'


def test_google_mode_requires_real_production_hosts(monkeypatch):
    monkeypatch.setenv('SEO_PULSE_CONNECTOR', 'google')
    monkeypatch.delenv('SEO_PULSE_PRODUCTION_HOSTS', raising=False)
    with pytest.raises(ValueError, match='SEO_PULSE_PRODUCTION_HOSTS'):
        get_connectors()


# --- weekly report ----------------------------------------------------------

def test_weekly_report_windows_baseline_and_daily_rows():
    gsc = FakeGSC([gsc_row('2026-09-14', clicks=40, impressions=400)])
    report = build_weekly_report(gsc, FakeGA4([]), settings(), end_date='2026-10-11')
    assert report['periods'] == {
        'current': {'start': '2026-10-05', 'end': '2026-10-11'},
        'previous': {'start': '2026-09-28', 'end': '2026-10-04'},
        'baseline': {'start': '2026-09-07', 'end': '2026-10-04', 'weeks': 4}}
    by_window = {(start, end): dims for start, end, dims in gsc.calls}
    assert 'date' in by_window[('2026-10-05', '2026-10-11')]  # A14 needs daily rows
    assert 'date' in by_window[('2026-09-28', '2026-10-04')]
    assert report['totals']['gsc']['baseline_weekly_avg']['clicks'] == 10  # 40 over 4 weeks, not the sum


def test_weekly_report_detects_daily_gap_and_counts():
    days = ['2026-10-05', '2026-10-06', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11']
    gsc = FakeGSC([gsc_row(d) for d in days] + [gsc_row('2026-10-01')])
    report = build_weekly_report(gsc, FakeGA4([]), settings(), end_date='2026-10-11')
    assert any(f['rule'] == 'A14' and f['entity'] == 'gsc:2026-10-07' for f in report['findings'])
    assert report['totals']['gsc']['current']['clicks'] == 60
    assert report['totals']['gsc']['previous']['clicks'] == 10
    assert report['totals']['gsc']['change_pct']['clicks'] == pytest.approx(500)
    assert any('本週 GSC 只有 6/7 天' in w for w in report['warnings'])


def test_weekly_report_on_fixture_keeps_quality_and_is_compact():
    gsc, ga4 = get_connectors()
    report = build_weekly_report(gsc, ga4, settings(), end_date='2026-10-11', top_n=2)
    assert report['fixture'] is True
    quality = report['data_quality']['current']
    assert quality['pollution_warning'] and quality['excluded_sessions'] == 770
    assert len(report['findings']) == 2 and report['findings_total'] > 2
    assert sum(report['priority_counts'].values()) == report['findings_total']
    assert all('data_quality' not in f for f in report['findings'])
    assert report['totals']['ga4']['current']['sessions'] == 140
    assert report['not_evaluated'] == []


def test_weekly_report_lists_rules_without_baseline():
    gsc = FakeGSC([gsc_row('2026-10-05')])
    report = build_weekly_report(gsc, FakeGA4([]), settings(), end_date='2026-10-11')
    assert {item['rules'] for item in report['not_evaluated']} >= {'A1/A2/A8'}


def test_weekly_report_rejects_bad_input():
    with pytest.raises(ValueError):
        build_weekly_report(FakeGSC([]), FakeGA4([]), settings(), end_date='2026/10/11')
    with pytest.raises(ValueError):
        build_weekly_report(FakeGSC([]), FakeGA4([]), settings(), end_date='2026-10-11', top_n=0)


def test_weekly_report_mcp_tool():
    report = server.weekly_report('2026-10-11')
    assert report['periods']['current']['end'] == '2026-10-11'
    assert report['findings'][0]['rank'] == 1
