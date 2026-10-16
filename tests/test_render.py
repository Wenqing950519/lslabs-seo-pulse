import re
from pathlib import Path

import pytest

from seo_pulse_mcp import server
from seo_pulse_mcp.branding import DISPLAY_NAME, FOOTER
from seo_pulse_mcp.render import render_markdown
from seo_pulse_mcp.rules import RULE_LABELS, RULES

REPO = Path(__file__).parents[1]


@pytest.fixture
def report():
    return server.weekly_report('2026-10-11')


def finding(**kw):
    base = dict(rule='A4', entity='查詢', severity='medium', current=11.0, previous=8.0, change_pct=37.5,
                traffic_impact=3, confidence=1.0, score=2.0, rank=1, priority='P1')
    return {**base, **kw}


# --- markdown rendering -----------------------------------------------------

def test_markdown_layout_on_fixture(report):
    md = render_markdown(report)
    assert md.startswith(f'# {DISPLAY_NAME}\n')
    assert '以下為假資料示範' in md
    assert '2026-10-05 – 2026-10-11' in md and '2026-09-28 – 2026-10-04' in md
    sections = re.findall(r'^## (.+)$', md, flags=re.M)
    assert sections == ['本週摘要', '關鍵數字', '資料品質', '異常與機會', '熱門頁面', '熱門查詢', '下週建議']
    assert '| 點擊 | 28 | 70 | -60.0% |' in md
    assert '| CTR | 6.67% | 10.00% | -33.3% |' in md
    assert '| Sessions | 140 |' in md
    for warning in report['warnings']:
        assert f'- {warning}' in md
    assert '### P0' in md and f"A10 {RULE_LABELS['A10']}" in md
    assert md.rstrip().endswith(FOOTER)


def test_markdown_is_deterministic(report):
    assert render_markdown(report) == render_markdown(report)


def test_markdown_real_data_and_empty_findings(report):
    real = {**report, 'fixture': False, 'findings': [], 'findings_total': 0,
            'priority_counts': {'P0': 0, 'P1': 0, 'P2': 0}, 'warnings': [], 'not_evaluated': []}
    md = render_markdown(real)
    assert '以下為假資料示範' not in md  # fixture query text itself contains 假資料
    assert '本週沒有觸發任何規則' in md
    assert '未發現資料品質問題' in md


def test_markdown_formats_missing_change_and_escapes_pipes(report):
    gsc = report['totals']['gsc']
    real = {**report, 'totals': {**report['totals'], 'gsc': {**gsc, 'change_pct': {**gsc['change_pct'], 'clicks': None}}},
            'findings': [finding(entity='a|b', change_pct=None)], 'findings_total': 1,
            'not_evaluated': [{'rules': 'A1/A2/A8', 'reason': '前四週沒有 GSC 資料。'}]}
    md = render_markdown(real)
    assert '| 點擊 | 28 | 70 | 上週無資料 |' in md
    assert 'a\\|b' in md
    assert '- 未評估 A1/A2/A8：前四週沒有 GSC 資料。' in md


def test_markdown_notes_truncated_findings(report):
    md = render_markdown({**report, 'findings': report['findings'][:1]})
    assert f"僅列出前 1 筆，共 {report['findings_total']} 筆" in md


def test_weekly_report_markdown_format():
    md = server.weekly_report('2026-10-11', format='markdown')
    assert isinstance(md, str) and md.startswith(f'# {DISPLAY_NAME}')
    with pytest.raises(ValueError, match='format'):
        server.weekly_report('2026-10-11', format='html')


# --- rule labels and template ----------------------------------------------

def test_every_rule_has_label():
    assert set(RULE_LABELS) == set(RULES['minimums'])


def test_rules_doc_matches_code():
    doc = (REPO / 'docs' / 'rules.md').read_text(encoding='utf-8')
    for rule, label in RULE_LABELS.items():
        row = next((line for line in doc.splitlines() if line.startswith(f'| {rule} |')), None)
        assert row, rule
        cells = [c.strip() for c in re.split(r'(?<!\\)\|', row.strip('|'))]
        assert cells[1] == label
        assert cells[3] == str(RULES['minimums'][rule])


# --- README -----------------------------------------------------------------

def test_readme_covers_windows_and_no_stale_paths():
    readme = (REPO / 'README.md').read_text(encoding='utf-8')
    assert r'.venv\Scripts\python.exe' in readme
    assert r'%APPDATA%\Claude\claude_desktop_config.json' in readme
    assert 'claude mcp add' in readme
    assert 'docs/rules.md' in readme
    assert '../growth/' not in readme and '/absolute/path/app' not in readme
