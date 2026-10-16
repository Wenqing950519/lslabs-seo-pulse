"""Source of truth: growth/weekly-report-template.md v0.1 (2026-10-16)."""
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
