"""Server-side weekly report: fetch, clean, baseline and evaluate in one pass.

Raw GSC/GA4 rows never leave the server; the AI receives totals, movers and ranked findings.
"""
from dataclasses import replace
from datetime import date, timedelta

from .anomalies import aggregate, detect_anomalies
from .hosts import clean_hosts
from .rules import RULES

GSC_DAILY = ["date", "query", "page"]
BASELINE_WEEKS = 4
TOP_MOVERS = 10


def _window(start, end):
    return {"start": start.isoformat(), "end": end.isoformat()}


def _change(now, old):
    return (now / old - 1) * 100 if old else None


def _gsc_totals(rows):
    site = aggregate(rows).get("site", {})
    return {k: site.get(k, 0) for k in ("clicks", "impressions", "ctr", "position")}


def _ga4_totals(rows, ai_sources):
    def total(metric, keep=lambda r: True):
        return sum(r.get(metric, 0) for r in rows if keep(r))
    organic = lambda r: r.get("sessionDefaultChannelGroup") == "Organic Search"
    return {"sessions": total("sessions"),
            "organic_sessions": total("sessions", organic),
            "google_organic_sessions": total("sessions", lambda r: organic(r) and r.get("sessionSource") == "google"),
            "ai_sessions": total("sessions", lambda r: r.get("sessionSource") in ai_sources),
            "key_events": total("keyEvents")}


def _movers(rows, old_rows, dimension, origin):
    new, old = aggregate(rows, dimension, origin), aggregate(old_rows, dimension, origin)
    ranked = sorted(new.items(), key=lambda kv: (-kv[1]["clicks"], -kv[1]["impressions"], kv[0]))
    return [{"entity": key, "clicks": item["clicks"], "previous_clicks": old.get(key, {}).get("clicks", 0),
             "impressions": item["impressions"], "position": round(item["position"], 1)}
            for key, item in ranked[:TOP_MOVERS]]


def build_weekly_report(gsc, ga4, settings, end_date=None, top_n=20, now=None, rules=None,
                        production_hosts=None):
    # Anomaly detection also filters GA4 rows. Use the same request-local settings
    # for both passes, including callers that invoke the report builder directly.
    if production_hosts is not None:
        settings = replace(settings, production_hosts=tuple(production_hosts))
    end = date.fromisoformat(end_date) if end_date else settings.default_end_date(now)
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    current = (end - timedelta(days=6), end)
    previous = (end - timedelta(days=13), end - timedelta(days=7))
    baseline_window = (end - timedelta(days=7 * BASELINE_WEEKS + 6), end - timedelta(days=7))

    iso = lambda window: (window[0].isoformat(), window[1].isoformat())
    gsc_now = gsc.query(*iso(current), GSC_DAILY)
    gsc_old = gsc.query(*iso(previous), GSC_DAILY)
    # Baseline is a weekly average of the four weeks before the current one, never their sum.
    baseline_rows = gsc.query(*iso(baseline_window), ["query", "page"])
    baseline_days = {r["date"] for r in gsc.query(*iso(baseline_window), ["date"])}
    baseline = None
    if baseline_rows:
        baseline = {"gsc": [{**r, "clicks": r["clicks"] / BASELINE_WEEKS,
                             "impressions": r["impressions"] / BASELINE_WEEKS} for r in baseline_rows]}

    # Measure data quality on raw rows before anomaly detection rechecks hosts.
    ga_now, quality_now = clean_hosts(ga4.report(*iso(current)), production_hosts, settings=settings)
    ga_old, quality_old = clean_hosts(ga4.report(*iso(previous)), production_hosts, settings=settings)

    findings = detect_anomalies({"gsc": gsc_now, "ga4": ga_now, "baseline": baseline, "data_quality": quality_now},
                                {"gsc": gsc_old, "ga4": ga_old}, rules, settings)
    for item in findings:
        item.pop("data_quality", None)

    not_evaluated, warnings = [], []
    if baseline is None:
        not_evaluated.append({"rules": "A1/A2/A8", "reason": "前四週沒有 GSC 資料，無法比較 baseline。"})
    elif len(baseline_days) < 7 * BASELINE_WEEKS:
        warnings.append(f"baseline 只有 {len(baseline_days)}/{7 * BASELINE_WEEKS} 天有資料，週平均可能偏低。")
    current_days = {r["date"] for r in gsc_now}
    if gsc_now and len(current_days) < 7:
        warnings.append(f"本週 GSC 只有 {len(current_days)}/7 天有資料；可能尚未更新或確實無曝光，請確認後再下結論。")
    if not gsc_now:
        not_evaluated.append({"rules": "A3-A9/A14", "reason": "本週沒有 GSC 資料。"})
    if not (ga_now or ga_old):
        not_evaluated.append({"rules": "A10-A13", "reason": "兩週都沒有正式網域的 GA4 資料。"})
    if quality_now["pollution_warning"]:
        warnings.append(f"資料污染警告：本週 GA4 有 {quality_now['pollution_ratio']:.0%} sessions 來自非正式網域。")
    # A chosen host list is a scope decision; only prompt when hosts were derived from site_url.
    if quality_now["subdomain_sessions"] and not settings.hosts_explicit:
        hosts = "、".join(quality_now["subdomain_hosts"])
        warnings.append(f"同網域其他子網域（{hosts}）本週 {quality_now['subdomain_sessions']:,} sessions 未計入 GA4；"
                        "Search Console 網域屬性會計入這些子網域，若它們也是正式站，請傳 production_hosts。")

    origin = settings.canonical_origin
    ai_sources = (rules or {}).get("ai_sources", RULES["ai_sources"])
    gsc_totals = {"current": _gsc_totals(gsc_now), "previous": _gsc_totals(gsc_old),
                  "baseline_weekly_avg": _gsc_totals(baseline["gsc"]) if baseline else None}
    gsc_totals["change_pct"] = {k: _change(gsc_totals["current"][k], gsc_totals["previous"][k])
                                for k in gsc_totals["current"]}
    ga4_totals = {"current": _ga4_totals(ga_now, ai_sources), "previous": _ga4_totals(ga_old, ai_sources)}
    ga4_totals["change_pct"] = {k: _change(ga4_totals["current"][k], ga4_totals["previous"][k])
                                for k in ga4_totals["current"]}
    return {
        "site": origin,
        "fixture": settings.connector == "fixture",
        "timezone": settings.timezone,
        "periods": {"current": _window(*current), "previous": _window(*previous),
                    "baseline": {**_window(*baseline_window), "weeks": BASELINE_WEEKS}},
        "totals": {"gsc": gsc_totals, "ga4": ga4_totals},
        "data_quality": {"current": quality_now, "previous": quality_old},
        "top_pages": _movers(gsc_now, gsc_old, "page", origin),
        "top_queries": _movers(gsc_now, gsc_old, "query", origin),
        "findings": findings[:top_n],
        "findings_total": len(findings),
        "priority_counts": {p: sum(f["priority"] == p for f in findings) for p in ("P0", "P1", "P2")},
        "not_evaluated": not_evaluated,
        "warnings": warnings,
    }
