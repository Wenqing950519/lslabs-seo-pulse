# SEO Pulse 異常規則 A1–A14

本檔是 A1–A14 的現行說明正本，依 `seo_pulse_mcp/anomalies.py` 與 `seo_pulse_mcp/rules.py` 的實作整理。最初的來源 `growth/weekly-report-template.md` v0.1（2026-10-16）沒有收進此 repo；兩者不一致時以程式為準，並同步更新本檔。`tests/test_render.py` 會檢查下表的名稱與最低量和程式相同。

## 規則

「本週／上週」指 `weekly_report` 的兩個連續 7 天區間；「前四週平均」指本週之前四週（含上週）的每週平均。最低量未達時不列出該發現。

| ID | 名稱 | 觸發條件 | 最低量 | 最低量計算對象 | 嚴重度 |
|---|---|---|---|---|---|
| A1 | 全站點擊下滑 | 全站 GSC 點擊比上週少 ≥30%，且比前四週平均少 ≥20%；沒有 baseline 時不評估 | 20 | 上週點擊 | high |
| A2 | 全站曝光下滑 | 全站 GSC 曝光比上週少 ≥30%，且比前四週平均少 ≥20%；沒有 baseline 時不評估 | 200 | 上週曝光 | high |
| A3 | 頁面點擊下滑 | 單一頁面點擊比上週少 ≥50% | 10 | 上週點擊 | medium |
| A4 | 查詢掉出前 10 名 | 查詢上週平均排名在前 10，本週大於 10 | 20 | 上週曝光 | medium |
| A5 | 前 10 名 CTR 偏低 | 本週排名在前 10，CTR 低於預期 CTR 的 50%（預期值見 `config/ctr_benchmarks.json`） | 100 | 本週曝光 | medium |
| A6 | 排名 11–20 的機會查詢 | 本週平均排名介於 11 與 20 | 50 | 本週曝光 | low |
| A7 | 查詢曝光歸零 | 上週有曝光的查詢本週曝光為 0 | 30 | 上週曝光 | medium |
| A8 | 新出現的查詢 | 上週與前四週都沒有曝光，本週出現；沒有 baseline 時不評估 | 20 | 本週曝光 | info |
| A9 | 非正式網址出現在搜尋結果 | GSC 網址的 scheme 或主機與 `SEO_PULSE_CANONICAL_ORIGIN` 不同（含 www 變體） | 1 | 該網址本週曝光 | medium |
| A10 | 自然搜尋 sessions 下滑 | GA4 Organic Search sessions 比上週少 ≥30% | 30 | 上週 sessions | high |
| A11 | 關鍵事件下滑 | GA4 關鍵事件比上週少 ≥40% | 5 | 上週關鍵事件 | high |
| A12 | AI 來源流量變化 | AI 來源（chatgpt.com、perplexity.ai 等）sessions 從 0 出現，或增減 ≥50% | 5 | 本週與上週較大者 | info |
| A13 | GSC 點擊與 GA4 自然搜尋落差 | \|GSC 點擊 − GA4 Google 自然搜尋 sessions\| ÷ GSC 點擊 > 50%，兩者都需 ≥20 | 20 | 兩者較小者 | low |
| A14 | 資料缺漏日 | 本週某天 GSC 曝光或 GA4 sessions 為 0，但前一天與後一天都有資料；區間頭尾的缺漏不判定 | 0 | — | high |

門檻集中在 `rules.py` 的 `minimums` 與 `thresholds`，可用 `detect_anomalies(rules=...)` 覆寫。

## 排序與優先序

1. 分數 = 權重 ×（log10(1 + 影響量) + 1）× 信心。權重：high 3、medium 2、low 1、info 0.5。
2. 影響量為本週與上週 GSC 點擊差；兩週都沒有點擊時改用曝光差 ÷ 10。
3. 信心依最低量計算對象：≥ 3 倍最低量為 1.0，≥ 1.5 倍為 0.8，其餘 0.6。
4. 排序時 A9、A14 一律置頂，其餘依分數由高到低。
5. 優先序：A9、A14，以及排名前 2 且嚴重度為 high 者為 **P0**；A5、A6、A8、A12 與嚴重度 low 者為 **P2**；其餘為 **P1**。

## 資料前提

- GSC 需取同一層級的每日 query／page 明細，不可混入已加總的全站列；排名以曝光加權，CTR 由點擊 ÷ 曝光重算。
- GA4 先依 `SEO_PULSE_PRODUCTION_HOSTS` 白名單清理，localhost、127.0.0.1 與 `SEO_PULSE_EXCLUDE_HOSTS` 一律排除；排除超過 20% 時發出資料污染警告。
- 缺少資料的規則列在 `weekly_report` 的 `not_evaluated`，週報不可宣稱已檢查。
