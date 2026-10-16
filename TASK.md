# Task: LS-Labs Reports MVP skeleton (work ONLY inside this directory: app/)
Read ../handoffs/2026-10-16-mvp-spec.md and ../CONTEXT.md first. Stay strictly within spec.
Build in Python (>=3.10), package name `lslabs_reports`, MIT LICENSE (copyright "LS-Labs").
1. MCP server skeleton (stdio, local run) using the official `mcp` Python SDK (FastMCP) if installable; otherwise structure so it plugs in later. Tools: list_sites, gsc_query(start_date,end_date,dimensions,filters), gsc_compare_weeks, ga4_report, ga4_compare_weeks, detect_anomalies.
2. Swappable connector layer: `connectors/base.py` abstract GSCConnector/GA4Connector interfaces; `connectors/fixture.py` reading JSON fixtures (default); `connectors/google.py` stub raising NotImplementedError with TODO for scopes webmasters.readonly & analytics.readonly only. NO real OAuth or network calls anywhere. Config via env var LSLABS_CONNECTOR=fixture|google.
3. GA4 host filter: exclude localhost/127.0.0.1 and configurable test domains (env LSLABS_EXCLUDE_HOSTS) before analysis.
4. `anomalies.py` deterministic detect_anomalies(current, previous, rules) -> list of anomalies with severity & priority. Rules in `rules.py` as a config dict, clearly marked PLACEHOLDER pending analyst template growth/weekly-report-template.md: clicks drop >=20% WoW, impressions drop >=20%, query/page avg position falling out of top 10, pages not indexed, GA4 sessions drop >=20%; min-volume threshold to avoid noise; priority ordering by severity then traffic impact.
5. pytest tests in tests/ with fixtures in tests/fixtures/ (sample lslabs.tw-like fake data, 2 weeks GSC + GA4 incl. localhost rows). Cover each rule (trigger and non-trigger), host exclusion, priority ordering, connector swap. Tests must pass: create .venv and run `.venv/bin/python -m pytest -q`.
6. .gitignore covering credentials (client_secret*.json, token*.json, .env, *.pem), .venv. README.md in Traditional Chinese (brief: what, run tests, run server, mount in Claude; note OAuth not yet implemented, publish app to "In production" to avoid 7-day expiry). Footer "由 LS-Labs 製作". skill/SKILL.md placeholder for Traditional Chinese weekly report.
Forbidden: git push, creating remote repos, publishing, deleting files outside app/, network calls other than pip install.
End with a <=5 line summary of what changed and what's not done, including the final pytest result line.

## UPDATE (supersedes item 4 placeholders)
The analyst template now exists: ../growth/weekly-report-template.md. It is the SOURCE OF TRUTH for detect_anomalies: implement all its anomaly rules (with min-traffic thresholds), GA4 test-domain filtering applied FIRST, its P0/P1/P2 scoring, and tests for every rule incl. its edge cases. CTR-by-position expected values are provisional: put them in a config file (e.g. lslabs_reports/config/ctr_benchmarks.json), overridable via env/path, with a note they get replaced after 4 weeks of real data. AI citation section: placeholder text '待 01 研究數據', not implemented. Continue from existing files; don't start over.

## UPDATE 2
Also: .gitignore must cover .env, credential *.json (client_secret*, token*, credentials*, service-account*), tokens, node_modules, .venv, run*.log, last.txt. Do NOT commit (the bot will).
