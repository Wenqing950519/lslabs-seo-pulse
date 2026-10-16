"""Thresholds for A1–A14; definitions in docs/rules.md (from growth/weekly-report-template.md v0.1, 2026-10-16)."""
RULES = {
    "timezone": "Asia/Taipei", "gsc_lag_days": 3,
    "production_hosts": ["example.com"], "canonical_origin": "https://example.com",
    "ai_sources": ["chatgpt.com", "perplexity.ai", "gemini.google.com",
                   "copilot.microsoft.com", "claude.ai"],
    "minimums": {"A1": 20, "A2": 200, "A3": 10, "A4": 20, "A5": 100,
                 "A6": 50, "A7": 30, "A8": 20, "A9": 1, "A10": 30,
                 "A11": 5, "A12": 5, "A13": 20, "A14": 0},
    "thresholds": {"A1": .30, "A2": .30, "baseline_drop": .20, "A3": .50,
                   "A5": .50, "A10": .30, "A11": .40, "A12": .50, "A13": .50},
}

# Display names; definitions and thresholds are documented in docs/rules.md.
RULE_LABELS = {
    "A1": "全站點擊下滑", "A2": "全站曝光下滑", "A3": "頁面點擊下滑",
    "A4": "查詢掉出前 10 名", "A5": "前 10 名 CTR 偏低", "A6": "排名 11–20 的機會查詢",
    "A7": "查詢曝光歸零", "A8": "新出現的查詢", "A9": "非正式網址出現在搜尋結果",
    "A10": "自然搜尋 sessions 下滑", "A11": "關鍵事件下滑", "A12": "AI 來源流量變化",
    "A13": "GSC 點擊與 GA4 自然搜尋落差", "A14": "資料缺漏日",
}
