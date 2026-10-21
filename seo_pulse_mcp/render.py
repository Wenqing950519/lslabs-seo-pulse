"""Deterministic Markdown layout for weekly_report; the AI only fills summary and recommendations."""
from .branding import DISPLAY_NAME, footer
from .caller import current_caller
from .rules import RULE_LABELS

POSITION_RULES = {"A4", "A6"}
RATE_RULES = {"A5"}
ENTITY_LABELS = {"site": "全站", "Google organic vs GSC": "GA4 Google 自然搜尋 vs GSC 點擊"}
SUMMARY_PLACEHOLDER = "> 由 AI 依下方數字撰寫 3 句內摘要。"
ADVICE_PLACEHOLDER = "> 由 AI 依「異常與機會」撰寫最多 5 條建議：頁面／查詢、本週／上週／變化%、可能原因（假設）、動作、規則 ID。"


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def _number(value):
    if value is None:
        return "—"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}"
    return f"{int(value):,}"


def _percent(value):
    return f"{value * 100:.2f}%"


def _change(value):
    return "上週無資料" if value is None else f"{value:+.1f}%".replace("+-", "-")


def _table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _finding_value(rule, value):
    if rule in RATE_RULES:
        return _percent(value)
    if rule in POSITION_RULES:
        return f"{value:.1f}"
    return _number(value)


def _totals(report):
    gsc, ga4 = report["totals"]["gsc"], report["totals"]["ga4"]
    base = gsc.get("baseline_weekly_avg") or {}
    gsc_rows = []
    for key, label, fmt in [("clicks", "點擊", _number), ("impressions", "曝光", _number),
                            ("ctr", "CTR", _percent), ("position", "平均排名", lambda v: f"{v:.1f}")]:
        gsc_rows.append([label, fmt(gsc["current"][key]), fmt(gsc["previous"][key]),
                         _change(gsc["change_pct"][key]), fmt(base[key]) if key in base else "—"])
    ga4_rows = [[label, _number(ga4["current"][key]), _number(ga4["previous"][key]), _change(ga4["change_pct"][key])]
                for key, label in [("sessions", "Sessions"), ("organic_sessions", "自然搜尋 sessions"),
                                   ("google_organic_sessions", "Google 自然搜尋 sessions"),
                                   ("ai_sessions", "AI 來源 sessions"), ("key_events", "關鍵事件")]]
    return (["### Google Search Console", ""] + _table(["指標", "本週", "上週", "變化", "前四週平均"], gsc_rows)
            + ["", "### GA4（已排除測試主機）", ""] + _table(["指標", "本週", "上週", "變化"], ga4_rows))


def _quality(report):
    lines = [f"- {w}" for w in report["warnings"]]
    lines += [f"- 未評估 {item['rules']}：{item['reason']}" for item in report["not_evaluated"]]
    if not lines:
        lines.append("- 未發現資料品質問題。")
    q_now, q_old = report["data_quality"]["current"], report["data_quality"]["previous"]
    lines.append(f"- GA4 排除 sessions：本週 {_number(q_now['excluded_sessions'])}（{q_now['excluded_ratio']:.1%}），"
                 f"上週 {_number(q_old['excluded_sessions'])}（{q_old['excluded_ratio']:.1%}）。")
    return lines


def _findings(report):
    findings = report["findings"]
    if not findings:
        return ["本週沒有觸發任何規則。"]
    lines = []
    for priority in ("P0", "P1", "P2"):
        group = [f for f in findings if f["priority"] == priority]
        if not group:
            continue
        rows = [[f["rank"], f"{f['rule']} {RULE_LABELS.get(f['rule'], '')}".strip(), ENTITY_LABELS.get(f["entity"], f["entity"]),
                 _finding_value(f["rule"], f["current"]), _finding_value(f["rule"], f["previous"]),
                 _change(f["change_pct"]), f"{f['confidence']:.1f}"] for f in group]
        lines += [f"### {priority}", ""] + _table(["#", "規則", "對象", "本週", "上週", "變化", "信心"], rows) + [""]
    if len(findings) < report["findings_total"]:
        lines.append(f"僅列出前 {len(findings)} 筆，共 {report['findings_total']} 筆。")
    return lines


def _movers(items, label):
    if not items:
        return ["本週沒有資料。"]
    rows = [[i["entity"], _number(i["clicks"]), _number(i["previous_clicks"]), _number(i["impressions"]),
             f"{i['position']:.1f}"] for i in items]
    return _table([label, "點擊", "上週點擊", "曝光", "平均排名"], rows)


def render_markdown(report):
    periods = report["periods"]
    span = lambda p: f"{p['start']} – {p['end']}"
    lines = [f"# {DISPLAY_NAME}", ""]
    if report.get("fixture"):
        lines += ["> 以下為假資料示範。", ""]
    lines += [f"網站：{report['site']}｜本週 {span(periods['current'])}｜上週 {span(periods['previous'])}｜時區 {report['timezone']}", ""]
    sections = [("本週摘要", [SUMMARY_PLACEHOLDER]), ("關鍵數字", _totals(report)), ("資料品質", _quality(report)),
                ("異常與機會", _findings(report)), ("熱門頁面", _movers(report["top_pages"], "頁面")),
                ("熱門查詢", _movers(report["top_queries"], "查詢")), ("下週建議", [ADVICE_PLACEHOLDER])]
    for title, body in sections:
        while body and body[-1] == "":
            body = body[:-1]
        lines += [f"## {title}", ""] + body + [""]
    edition = "cloud" if current_caller() is not None else "local"
    return "\n".join(lines + ["---", "", footer(edition)]) + "\n"
