from pathlib import Path
import pytest
from seo_pulse_mcp.connectors import get_connectors
from seo_pulse_mcp.connectors.fixture import FixtureGSCConnector, FixtureGA4Connector
from seo_pulse_mcp.hosts import clean_hosts
from seo_pulse_mcp.anomalies import detect_anomalies

PATH=Path(__file__).parent/'fixtures/sample.json'


def test_fixture_dates_dimensions_filters():
    gsc=FixtureGSCConnector(PATH)
    assert gsc.list_sites()[0]['fake']
    result=gsc.query('2026-09-28','2026-10-04',['query'],{'page':'https://example.com/'})
    assert result[0]['clicks']==70
    assert result[0]['position']==8
    assert gsc.query('2026-01-01','2026-01-02',[])==[]
    with pytest.raises(ValueError): gsc.query('2026-10-04','2026-09-28',[])
    with pytest.raises(ValueError): gsc.query('2026-09-28','2026-10-04',['unsupported'])


def test_connector_swap(monkeypatch):
    monkeypatch.delenv('SEO_PULSE_CONNECTOR',raising=False)
    assert isinstance(get_connectors()[0],FixtureGSCConnector)
    GoogleGSCConnector=pytest.importorskip('seo_pulse_mcp.connectors.google').GoogleGSCConnector
    monkeypatch.setenv('SEO_PULSE_PRODUCTION_HOSTS','lslabs.tw')
    monkeypatch.setenv('SEO_PULSE_CONNECTOR','google')
    gsc,ga4=get_connectors()
    assert isinstance(gsc,GoogleGSCConnector)
    monkeypatch.setenv('SEO_PULSE_CONNECTOR','invalid')
    with pytest.raises(ValueError): get_connectors()


def test_filter_quality_and_override(monkeypatch):
    rows=FixtureGA4Connector(PATH).report('2026-09-28','2026-10-04')
    kept,quality=clean_hosts(rows)
    assert {r['hostName'] for r in kept}=={'example.com'}
    assert quality['excluded_sessions']==770
    assert quality['excluded_ratio']==770/1050
    assert quality['pollution_warning']
    monkeypatch.setenv('SEO_PULSE_EXCLUDE_HOSTS','example.com')
    assert clean_hosts(rows)[0]==[]
    assert clean_hosts([])[1]['excluded_ratio']==0


def test_filter_first():
    old=[dict(hostName='localhost',sessions=1000,keyEvents=100)]
    result=detect_anomalies({'ga4':[]},{'ga4':old})
    assert not result


def test_pollution_boundary():
    rows=[dict(hostName='example.com',sessions=80),dict(hostName='test.vercel.app',sessions=20)]
    assert not clean_hosts(rows)[1]['pollution_warning']
    rows[1]['sessions']=21
    assert clean_hosts(rows)[1]['pollution_warning']
