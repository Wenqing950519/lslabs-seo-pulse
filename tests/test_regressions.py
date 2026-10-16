import subprocess
import sys
from pathlib import Path

from seo_pulse_mcp import server
from seo_pulse_mcp.anomalies import detect_anomalies
from seo_pulse_mcp.hosts import clean_hosts

REPO = Path(__file__).parents[1]


def gsc(page, day):
    return dict(date=day, query='查詢', page=page, clicks=5, impressions=50, position=5)


def test_production_hosts_ignore_spaces_after_commas(monkeypatch):
    monkeypatch.setenv('SEO_PULSE_PRODUCTION_HOSTS', 'lslabs.tw, www.lslabs.tw')
    rows = [{'hostName': 'lslabs.tw', 'sessions': 10}, {'hostName': 'www.lslabs.tw', 'sessions': 10}]
    kept, quality = clean_hosts(rows)
    assert [r['hostName'] for r in kept] == ['lslabs.tw', 'www.lslabs.tw']
    assert quality['excluded_sessions'] == 0


def test_canonical_origin_follows_production_host(monkeypatch):
    # Real sites must not have every page flagged as an A9 URL problem.
    monkeypatch.setenv('SEO_PULSE_PRODUCTION_HOSTS', 'lslabs.tw')
    page = 'https://lslabs.tw/blog/a/'
    current = {'gsc': [gsc(page, '2026-10-05')]}
    previous = {'gsc': [gsc(page, '2026-09-28')]}
    assert not [f for f in detect_anomalies(current, previous) if f['rule'] == 'A9']


def test_canonical_origin_env_override(monkeypatch):
    monkeypatch.setenv('SEO_PULSE_PRODUCTION_HOSTS', 'lslabs.tw,www.lslabs.tw')
    monkeypatch.setenv('SEO_PULSE_CANONICAL_ORIGIN', 'https://www.lslabs.tw')
    current = {'gsc': [gsc('https://www.lslabs.tw/', '2026-10-05'), gsc('https://lslabs.tw/', '2026-10-05')]}
    a9 = [f['entity'] for f in detect_anomalies(current, {'gsc': []}) if f['rule'] == 'A9']
    assert a9 == ['https://lslabs.tw/']


def test_compare_weeks_quality_survives_detect_anomalies():
    ga = server.ga4_compare_weeks('2026-10-11')
    assert ga['data_quality']['current']['pollution_warning']
    current = {'gsc': [], 'ga4': ga['current'], 'data_quality': ga['data_quality']['current']}
    findings = server.detect_anomalies(current, {'gsc': [], 'ga4': ga['previous']})
    assert findings
    assert all(f['data_quality'] == ga['data_quality']['current'] for f in findings)


def test_fixture_server_runs_without_google_extras():
    code = ("import sys; sys.modules['google'] = None; sys.modules['googleapiclient'] = None; "
            "sys.modules['google_auth_oauthlib'] = None; "
            "from seo_pulse_mcp import server; assert server.list_sites()[0]['fake']")
    result = subprocess.run([sys.executable, '-c', code], cwd=REPO, capture_output=True, text=True,
                            env={'SEO_PULSE_CONNECTOR': 'fixture', 'PYTHONUTF8': '1',
                                 'SYSTEMROOT': __import__('os').environ.get('SYSTEMROOT', '')})
    assert result.returncode == 0, result.stderr
