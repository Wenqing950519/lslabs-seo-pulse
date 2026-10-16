"""Deterministic A1–A14 evaluation. Snapshots contain gsc/ga4 row lists.
current.baseline is the preceding four-week average snapshot (not their sum).
Without a baseline, A1/A2/A8 are skipped rather than inventing evidence.
A13 uses abs(clicks - Google organic sessions) / clicks.
"""
import json
import math
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from .hosts import clean_hosts
from .rules import RULES


def canonical_page(value, origin):
    url = urlsplit(value)
    host = (url.hostname or '').removeprefix('www.')
    canonical = urlsplit(origin)
    if host == canonical.hostname:
        return origin.rstrip('/') + (url.path.rstrip('/') or '/') + (('?' + url.query) if url.query else '')
    return value.rstrip('/')


def aggregate(rows, dimension=None, origin='https://example.com'):
    groups = {}
    for row in rows:
        if dimension and dimension not in row:
            continue
        key = canonical_page(row[dimension], origin) if dimension == 'page' else row.get(dimension, 'site')
        item = groups.setdefault(key, dict(clicks=0, impressions=0, position=0))
        item['clicks'] += row.get('clicks', 0)
        item['impressions'] += row.get('impressions', 0)
        item['position'] += row.get('position', 0) * row.get('impressions', 0)
    for item in groups.values():
        item['position'] = item['position'] / item['impressions'] if item['impressions'] else 0
        item['ctr'] = item['clicks'] / item['impressions'] if item['impressions'] else 0
    return groups


def detect_anomalies(current, previous, rules=None):
    cfg = {**RULES, **(rules or {})}
    mins = {**RULES['minimums'], **cfg['minimums']}
    thresholds = {**RULES['thresholds'], **cfg['thresholds']}
    path = cfg.get('ctr_benchmarks_path') or os.getenv('SEO_PULSE_CTR_BENCHMARKS_PATH')
    benchmarks = json.loads(Path(path or Path(__file__).parent / 'config/ctr_benchmarks.json').read_text(encoding='utf-8'))['expected_ctr_by_position']
    benchmarks = cfg.get('expected_ctr_by_position', benchmarks)
    origin = cfg['canonical_origin']
    hosts = cfg['production_hosts'] if rules and 'production_hosts' in rules else None
    ga, quality = clean_hosts(current.get('ga4', []), hosts)
    old_ga, _ = clean_hosts(previous.get('ga4', []), hosts)
    baseline = current.get('baseline')
    rows, old_rows = current.get('gsc', []), previous.get('gsc', [])
    site = aggregate(rows).get('site', {})
    old_site = aggregate(old_rows).get('site', {})
    findings = []
    severity = {a: ('high' if a in ('A1','A2','A10','A11','A14') else
                    'low' if a in ('A6','A13') else 'info' if a in ('A8','A12') else 'medium')
                for a in mins}

    def emit(rule, entity, now, old, volume, new_stats=None, old_stats=None):
        if volume < mins[rule]:
            return
        new_stats, old_stats = new_stats or {}, old_stats or {}
        # Click difference; if neither period has clicks, use impressions / 10.
        delta = abs(new_stats.get('clicks', 0) - old_stats.get('clicks', 0))
        if not (new_stats.get('clicks', 0) or old_stats.get('clicks', 0)):
            delta = abs(new_stats.get('impressions', 0) - old_stats.get('impressions', 0)) / 10
        minimum = mins[rule]
        confidence = 1.0 if volume >= minimum * 3 else .8 if volume >= minimum * 1.5 else .6
        weight = {'high': 3, 'medium': 2, 'low': 1, 'info': .5}[severity[rule]]
        findings.append(dict(rule=rule, entity=entity, severity=severity[rule], current=now,
                             previous=old, change_pct=(now / old - 1) * 100 if old else None,
                             traffic_impact=delta, confidence=confidence,
                             score=weight * (math.log10(1 + delta) + 1) * confidence,
                             possible_cause='需人工確認內容、搜尋需求或追蹤設定',
                             recommendation='檢查對應頁面／查詢及資料來源後提出修正建議'))

    def drop(now, old, amount):
        return old > 0 and now <= old * (1 - amount) + 1e-12

    for rule, metric in [('A1','clicks'), ('A2','impressions')]:
        n, o = site.get(metric, 0), old_site.get(metric, 0)
        base = aggregate(baseline.get('gsc', [])).get('site', {}).get(metric, 0) if baseline is not None else 0
        if drop(n, o, thresholds[rule]) and drop(n, base, thresholds['baseline_drop']):
            emit(rule, 'site', n, o, o, site, old_site)
    for dimension in ('page', 'query'):
        new, old = aggregate(rows, dimension, origin), aggregate(old_rows, dimension, origin)
        base = aggregate(baseline.get('gsc', []), dimension, origin) if baseline is not None else {}
        for entity in sorted(new.keys() | old.keys()):
            n, o = new.get(entity, {}), old.get(entity, {})
            nc, oc = n.get('clicks', 0), o.get('clicks', 0)
            ni, oi = n.get('impressions', 0), o.get('impressions', 0)
            if dimension == 'page':
                if drop(nc, oc, thresholds['A3']): emit('A3', entity, nc, oc, oc, n, o)
                continue
            if 0 < o.get('position', 0) <= 10 and n.get('position', 0) > 10:
                emit('A4', entity, n['position'], o['position'], oi, n, o)
            pos = n.get('position', 0)
            expected = benchmarks['1'] if pos <= 1 else benchmarks['2-3'] if pos <= 3 else benchmarks['4-10']
            if 0 < pos <= 10 and n['ctr'] < expected * thresholds['A5']:
                emit('A5', entity, n['ctr'], o.get('ctr', 0), ni, n, o)
            if 11 <= pos <= 20: emit('A6', entity, pos, o.get('position', 0), ni, n, o)
            if ni == 0: emit('A7', entity, ni, oi, oi, n, o)
            if baseline is not None and oi == 0 and base.get(entity, {}).get('impressions', 0) == 0:
                emit('A8', entity, ni, oi, ni, n, o)
    canonical = urlsplit(origin)
    bad = {}
    for row in rows:
        page = row.get('page')
        if page:
            url = urlsplit(page)
            if url.scheme != canonical.scheme or url.netloc != canonical.netloc:
                bad.setdefault(page, []).append(row)
    for page, values in sorted(bad.items()):
        n = aggregate(values)['site']
        emit('A9', page, n['impressions'], 0, n['impressions'], n)

    def total(data, metric, predicate=lambda r: True):
        return sum(r.get(metric, 0) for r in data if predicate(r))
    organic = lambda r: r.get('sessionDefaultChannelGroup') == 'Organic Search'
    google = lambda r: organic(r) and r.get('sessionSource') == 'google'
    ai = lambda r: r.get('sessionSource') in cfg['ai_sources']
    for rule, metric, predicate in [('A10','sessions',organic), ('A11','keyEvents',lambda r: True), ('A12','sessions',ai)]:
        n, o = total(ga, metric, predicate), total(old_ga, metric, predicate)
        trigger = drop(n, o, thresholds[rule]) if rule != 'A12' else (o == 0 and n > 0 or o > 0 and abs(n-o) + 1e-12 >= o * thresholds[rule])
        if trigger: emit(rule, 'site', n, o, max(n,o) if rule == 'A12' else o, site, old_site)
    clicks, sessions = site.get('clicks', 0), total(ga, 'sessions', google)
    if clicks >= mins['A13'] and sessions >= mins['A13'] and abs(clicks-sessions) > clicks * thresholds['A13']:
        emit('A13', 'Google organic vs GSC', sessions, clicks, min(clicks,sessions), site, old_site)
    for source, data, metric in [('gsc', rows, 'impressions'), ('ga4', ga, 'sessions')]:
        daily = {}
        for row in data:
            if 'date' in row:
                day = date.fromisoformat(row['date'])
                daily[day] = daily.get(day, 0) + row.get(metric, 0)
        for day in sorted(daily):
            middle = day + timedelta(days=1)
            if daily[day] > 0 and daily.get(day + timedelta(days=2), 0) > 0 and daily.get(middle, 0) == 0:
                emit('A14', f'{source}:{middle}', 0, daily[day], 0, site, old_site)
    findings.sort(key=lambda a: (a['rule'] not in ('A9','A14'), -a['score'], a['rule'], a['entity']))
    for rank, item in enumerate(findings, 1):
        item['rank'] = rank
        item['priority'] = ('P0' if item['rule'] in ('A9','A14') or rank <= 2 and item['severity'] == 'high'
                            else 'P2' if item['rule'] in ('A5','A6','A8','A12') or item['severity'] == 'low' else 'P1')
        item['data_quality'] = quality
    return findings
