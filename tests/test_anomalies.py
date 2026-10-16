from copy import deepcopy
import json
import pytest
from seo_pulse_mcp.anomalies import detect_anomalies, aggregate


def row(clicks=30, impressions=200, position=5, **kw):
    return dict(query='查詢',page='https://example.com/',clicks=clicks,impressions=impressions,position=position,**kw)


def ga(sessions=40, events=10, source='google', **kw):
    return dict(hostName='example.com',sessions=sessions,keyEvents=events,
                sessionDefaultChannelGroup='Organic Search',sessionSource=source,**kw)


def snapshot(g=None,a=None):
    return dict(gsc=g or [],ga4=a or [])


def case(rule):
    old=snapshot([row()], [ga()]); now=deepcopy(old)
    now['baseline']=deepcopy(old)
    if rule=='A1': now['gsc'][0]['clicks']=21
    if rule=='A2': now['gsc'][0]['impressions']=140
    if rule=='A3': now['gsc'][0]['clicks']=15
    if rule=='A4': now['gsc'][0]['position']=10.01
    if rule=='A5': now['gsc'][0]['clicks']=3
    if rule=='A6': now['gsc'][0]['position']=11
    if rule=='A7': now['gsc']=[]
    if rule=='A8': old['gsc']=[]; now['baseline']['gsc']=[]
    if rule=='A9': now['gsc'][0]['page']='http://www.example.com/'
    if rule=='A10': now['ga4'][0]['sessions']=28
    if rule=='A11': now['ga4'][0]['keyEvents']=6
    if rule=='A12': old['ga4']=[ga(10,source='chatgpt.com')]; now['ga4']=[ga(15,source='chatgpt.com')]
    if rule=='A13': now['ga4'][0]['sessions']=46
    if rule=='A14': now['gsc']=[row(date='2026-10-01'),row(date='2026-10-03')]
    return now,old


@pytest.mark.parametrize('rule',[f'A{i}' for i in range(1,15)])
def test_each_trigger(rule):
    now,old=case(rule)
    assert rule in {a['rule'] for a in detect_anomalies(now,old)}


@pytest.mark.parametrize('rule',[f'A{i}' for i in range(1,15)])
def test_each_nontrigger(rule):
    old=snapshot([row()], [ga()]); now=deepcopy(old); now['baseline']=deepcopy(old)
    assert rule not in {a['rule'] for a in detect_anomalies(now,old)}


@pytest.mark.parametrize('rule',[f'A{i}' for i in range(1,14)])
def test_each_minimum(rule):
    now,old=case(rule)
    assert rule not in {a['rule'] for a in detect_anomalies(now,old,{'minimums':{rule:10000}})}


@pytest.mark.parametrize('rule,field,value',[
 ('A1','clicks',21.001),('A2','impressions',140.001),('A3','clicks',15.001),
 ('A4','position',10),('A5','clicks',4),('A6','position',20.01)])
def test_gsc_boundaries(rule,field,value):
    now,old=case(rule);now['gsc'][0][field]=value
    assert rule not in {a['rule'] for a in detect_anomalies(now,old)}


@pytest.mark.parametrize('rule,field,value',[
 ('A10','sessions',28.001),('A11','keyEvents',6.001),('A12','sessions',14.999),('A13','sessions',45)])
def test_ga_boundaries(rule,field,value):
    now,old=case(rule);now['ga4'][0][field]=value
    assert rule not in {a['rule'] for a in detect_anomalies(now,old)}


def test_baseline_required_and_new_baseline_query():
    now,old=case('A1');now.pop('baseline')
    assert 'A1' not in {a['rule'] for a in detect_anomalies(now,old)}
    now,old=case('A8');now['baseline']=deepcopy(now);now['baseline'].pop('baseline',None)
    assert 'A8' not in {a['rule'] for a in detect_anomalies(now,old)}


def test_normalization_weighted_position():
    rows=[row(10,100,5),row(20,200,8)]
    rows[1]['page']='http://www.example.com/'
    result=aggregate(rows,'page')['https://example.com/']
    assert result==dict(clicks=30,impressions=300,position=7,ctr=.1)


def test_ctr_override(tmp_path,monkeypatch):
    p=tmp_path/'ctr.json';p.write_text(json.dumps({'expected_ctr_by_position':{'1':0,'2-3':0,'4-10':0}}))
    monkeypatch.setenv('SEO_PULSE_CTR_BENCHMARKS_PATH',str(p))
    assert 'A5' not in {a['rule'] for a in detect_anomalies(*case('A5'))}


def test_priorities_score_and_determinism():
    now,old=case('A1');now['gsc'][0]['page']='http://example.com/'
    now['ga4'][0]['sessions']=10
    result=detect_anomalies(now,old)
    assert result==detect_anomalies(now,old)
    assert result[0]['rule']=='A9' and result[0]['priority']=='P0'
    for item in result:
        assert item['priority'] in {'P0','P1','P2'}
        assert item['confidence'] in {.6,.8,1}
    assert [a['score'] for a in result[1:]]==sorted([a['score'] for a in result[1:]],reverse=True)


def test_a14_zero_and_no_edge_inference():
    now,old=case('A14');now['gsc'].insert(1,row(0,0,date='2026-10-02'))
    assert 'A14' in {a['rule'] for a in detect_anomalies(now,old)}
    now['gsc']=now['gsc'][:2]
    assert 'A14' not in {a['rule'] for a in detect_anomalies(now,old)}


@pytest.mark.parametrize('rule,volume',[
 ('A1',20),('A2',200),('A3',10),('A4',20),('A5',100),('A6',50),
 ('A7',30),('A8',20),('A9',1),('A10',30),('A11',5),('A12',5),('A13',20)])
def test_actual_minimum_boundary(rule,volume):
    def build(v):
        now,old=case(rule)
        n=now['gsc'][0] if now['gsc'] else None
        o=old['gsc'][0] if old['gsc'] else None
        if rule=='A1': o['clicks']=v;n['clicks']=v*.7
        elif rule=='A2': o['impressions']=v;n['impressions']=v*.7
        elif rule=='A3': o['clicks']=v;n['clicks']=v*.5
        elif rule=='A4': o['impressions']=v
        elif rule=='A5': n['impressions']=v;n['clicks']=0
        elif rule=='A6': n['impressions']=v
        elif rule=='A7': o['impressions']=v
        elif rule=='A8': n['impressions']=v
        elif rule=='A9': n['impressions']=v
        elif rule=='A10': old['ga4'][0]['sessions']=v;now['ga4'][0]['sessions']=v*.7
        elif rule=='A11': old['ga4'][0]['keyEvents']=v;now['ga4'][0]['keyEvents']=v*.6
        elif rule=='A12': old['ga4'][0]['sessions']=v/1.5;now['ga4'][0]['sessions']=v
        elif rule=='A13': n['clicks']=v;now['ga4'][0]['sessions']=v*2
        return now,old
    assert rule in {a['rule'] for a in detect_anomalies(*build(volume))}
    assert rule not in {a['rule'] for a in detect_anomalies(*build(volume-.001))}


def test_a12_zero_baseline_and_decline():
    now,old=case('A12');old['ga4'][0]['sessions']=0;now['ga4'][0]['sessions']=5
    item=next(a for a in detect_anomalies(now,old) if a['rule']=='A12')
    assert item['change_pct'] is None and item['priority']=='P2'
    old['ga4'][0]['sessions']=10
    assert 'A12' in {a['rule'] for a in detect_anomalies(now,old)}


def test_a14_ga4_missing_day_after_host_cleaning():
    old=snapshot()
    now=snapshot(a=[ga(date='2026-10-01'),ga(date='2026-10-03'),
                    {**ga(date='2026-10-02'),'hostName':'localhost'}])
    assert any(a['entity']=='ga4:2026-10-02' for a in detect_anomalies(now,old))


def test_score_formula_confidence_and_opportunity():
    import math
    now,old=case('A3')
    item=next(a for a in detect_anomalies(now,old) if a['rule']=='A3')
    assert item['confidence']==1
    assert item['score']==2*(math.log10(16)+1)
    now,old=case('A5')
    assert next(a for a in detect_anomalies(now,old) if a['rule']=='A5')['priority']=='P2'
