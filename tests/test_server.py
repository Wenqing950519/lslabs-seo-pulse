from lslabs_reports import server


def test_server_tools():
    assert server.list_sites()[0]['fake']
    gsc=server.gsc_compare_weeks('2026-10-11')
    assert gsc['previous'][0]['clicks']==70
    assert gsc['current'][0]['clicks']==28
    ga=server.ga4_compare_weeks('2026-10-11')
    assert sum(r['sessions'] for r in ga['current'])==140
    assert ga['data_quality']['current']['excluded_sessions']==770
    assert {r['hostName'] for r in server.ga4_report('2026-09-28','2026-10-11')}=={'lslabs.tw'}
    anomalies=server.detect_anomalies({'gsc':gsc['current'],'ga4':ga['current'],
                                     'baseline':{'gsc':gsc['previous']}},
                                    {'gsc':gsc['previous'],'ga4':ga['previous']})
    assert {'A1','A2','A3','A4','A6','A10','A11'} <= {a['rule'] for a in anomalies}
