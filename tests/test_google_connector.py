import os
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest
g = pytest.importorskip('seo_pulse_mcp.connectors.google')
creds = pytest.importorskip('seo_pulse_mcp.connectors.credentials')


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv('SEO_PULSE_TOKEN_DIR', str(tmp_path / 'tokens'))
    monkeypatch.delenv('SEO_PULSE_GOOGLE_CLIENT_SECRET', raising=False)
    with patch.object(creds.InstalledAppFlow, 'from_client_secrets_file', side_effect=AssertionError('No sign-in')), \
         patch.object(creds, 'Request', side_effect=AssertionError('No network')), \
         patch('socket.socket.connect', side_effect=AssertionError('No network')):
        yield


def test_exact_scopes():
    assert g.GSC_SCOPES == ('https://www.googleapis.com/auth/webmasters.readonly',)
    assert g.GA4_SCOPES == ('https://www.googleapis.com/auth/analytics.readonly',)


def test_tools_never_login(monkeypatch):
    monkeypatch.setenv('SEO_PULSE_GSC_SITE_URL', 'sc-domain:example.com')
    monkeypatch.setenv('SEO_PULSE_GA4_PROPERTY_ID', '123')
    for action in (g.GoogleGSCConnector().list_sites,
                   lambda: g.GoogleGSCConnector().query('2026-01-01', '2026-01-02', []),
                   lambda: g.GoogleGA4Connector().report('2026-01-01', '2026-01-02')):
        with pytest.raises(RuntimeError, match='seo-pulse auth'):
            action()


def test_missing_secret():
    with pytest.raises(RuntimeError, match='SEO_PULSE_GOOGLE_CLIENT_SECRET'):
        g.authenticate()


def test_refresh(tmp_path):
    path = tmp_path / 'tokens' / 'gsc.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'scopes': list(g.GSC_SCOPES)}))
    credentials = Mock(expired=True, refresh_token='refresh', valid=True)
    credentials.to_json.return_value = '{"refreshed": true}'
    with patch.object(creds.Credentials, 'from_authorized_user_info', return_value=credentials) as load, \
         patch.object(creds, 'Request', return_value='transport'):
        assert g._credentials('gsc') is credentials
    credentials.refresh.assert_called_once_with('transport')
    assert load.call_args.kwargs['scopes'] == list(g.GSC_SCOPES)
    assert json.loads(path.read_text()) == {'refreshed': True}
    if os.name != 'nt':  # Windows has no POSIX mode bits; the user-profile ACL protects tokens there.
        assert path.stat().st_mode & 0o777 == 0o600


def test_broader_token_rejected(tmp_path):
    path = tmp_path / 'tokens' / 'gsc.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'scopes': [*g.GSC_SCOPES, 'extra']}))
    with pytest.raises(RuntimeError, match='seo-pulse auth'):
        g._credentials('gsc')


def test_explicit_auth(tmp_path, monkeypatch):
    secret = tmp_path / 'client_secret.json'
    secret.write_text('{}')
    monkeypatch.setenv('SEO_PULSE_GOOGLE_CLIENT_SECRET', str(secret))
    credentials = Mock()
    credentials.to_json.return_value = '{}'
    flow = Mock()
    flow.run_local_server.return_value = credentials
    with patch.object(creds.InstalledAppFlow, 'from_client_secrets_file', return_value=flow) as factory:
        g.authenticate()
    assert [call.kwargs['scopes'] for call in factory.call_args_list] == [list(g.GSC_SCOPES), list(g.GA4_SCOPES)]
    assert flow.run_local_server.call_count == 2


def test_gsc_mapping_paging():
    client, factory = Mock(), Mock()
    factory.return_value = client
    raw = {'keys': ['term'], 'clicks': 2, 'impressions': 10, 'position': 4, 'ctr': 99}
    client.searchanalytics.return_value.query.return_value.execute.side_effect = [
        {'rows': [raw] * 25000}, {'rows': [{**raw, 'impressions': 0}]}]
    client.sites.return_value.list.return_value.execute.return_value = {
        'siteEntry': [{'siteUrl': 'sc-domain:example.com', 'permissionLevel': 'siteOwner'}]}
    connector = g.GoogleGSCConnector(factory, 'sc-domain:example.com')
    with patch.object(creds, '_credentials', return_value='credentials'):
        assert connector.list_sites()[0]['siteUrl'] == 'sc-domain:example.com'
        rows = connector.query('2026-01-01', '2026-01-02', ['query'], {'page': 'https://example.com/'})
    assert rows[0] == dict(query='term', clicks=2, impressions=10, position=4, ctr=.2)
    assert rows[-1]['ctr'] == 0
    calls = client.searchanalytics.return_value.query.call_args_list
    assert [c.kwargs['body']['startRow'] for c in calls] == [0, 25000]
    assert calls[0].kwargs['body']['rowLimit'] == 25000
    assert calls[0].kwargs['body']['dimensionFilterGroups'][0]['filters'][0]['operator'] == 'equals'
    assert factory.call_args.args == ('searchconsole', 'v1')


def test_ga4_mapping_paging_and_hosts():
    from seo_pulse_mcp.hosts import clean_hosts
    def row(host):
        return NS(dimension_values=[NS(value=v) for v in ['20260101', host, 'Organic Search', 'google']],
                  metric_values=[NS(value='12'), NS(value='1.5')])
    client = Mock()
    client.run_report.side_effect = [NS(rows=[row('example.com')], row_count=2),
                                     NS(rows=[row('localhost')], row_count=2)]
    factory = Mock(return_value=client)
    with patch.object(creds, '_credentials', return_value='credentials'):
        rows = g.GoogleGA4Connector(factory, '123').report('2026-01-01', '2026-01-02')
    assert rows[0] == dict(date='2026-01-01', hostName='example.com',
                          sessionDefaultChannelGroup='Organic Search', sessionSource='google',
                          sessions=12, keyEvents=1.5)
    assert len(clean_hosts(rows)[0]) == 1
    requests = [call.kwargs['request'] for call in client.run_report.call_args_list]
    assert [r['offset'] for r in requests] == [0, 1]
    assert requests[0]['property'] == 'properties/123'
    assert {'name': 'hostName'} in requests[0]['dimensions']


def test_cli_auth():
    from seo_pulse_mcp.server import main
    with patch('sys.argv', ['seo-pulse', 'auth']), patch.object(g, 'authenticate') as auth:
        main()
    auth.assert_called_once_with()


def test_failed_refresh_requires_auth(tmp_path):
    path = tmp_path / 'tokens' / 'ga4.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'scopes': list(g.GA4_SCOPES)}))
    credentials = Mock(expired=True, refresh_token='revoked', valid=False)
    credentials.refresh.side_effect = creds.RefreshError('revoked')
    with patch.object(creds.Credentials, 'from_authorized_user_info', return_value=credentials), \
         patch.object(creds, 'Request', return_value='transport'):
        with pytest.raises(RuntimeError, match='seo-pulse auth'):
            g._credentials('ga4')


def test_valid_cache_no_refresh(tmp_path):
    path = tmp_path / 'tokens' / 'ga4.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'scopes': list(g.GA4_SCOPES)}))
    credentials = Mock(expired=False, valid=True)
    with patch.object(creds.Credentials, 'from_authorized_user_info', return_value=credentials):
        assert g._credentials('ga4') is credentials
    credentials.refresh.assert_not_called()


def test_custom_credential_provider_injected():
    """A9: connectors accept any CredentialProvider, not just LocalFileCredentialProvider."""
    calls = []

    class FakeProvider(creds.CredentialProvider):
        def get(self, service, context=None):
            calls.append((service, context))
            return 'fake-credentials'

    gsc_factory = Mock()
    gsc_factory.return_value.sites.return_value.list.return_value.execute.return_value = {'siteEntry': []}
    gsc = g.GoogleGSCConnector(gsc_factory, 'sc-domain:example.com', credential_provider=FakeProvider())
    gsc.list_sites()

    ga4_factory = Mock()
    ga4_factory.return_value.run_report.return_value = NS(rows=[], row_count=0)
    ga4 = g.GoogleGA4Connector(ga4_factory, '123', credential_provider=FakeProvider())
    ga4.report('2026-01-01', '2026-01-02')

    assert calls == [('gsc', None), ('ga4', None)]
    assert gsc_factory.call_args.kwargs['credentials'] == 'fake-credentials'
    assert ga4_factory.call_args.kwargs['credentials'] == 'fake-credentials'
