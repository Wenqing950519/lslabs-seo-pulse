---
name: seo-pulse-weekly-report
description: LS-Labs SEO Pulse 流量脈搏繁中行銷週報骨架，以本機 MCP 的 GSC／GA4 資料產出週報建議。
---

週報標題：LS-Labs SEO Pulse 流量脈搏。顯示名稱可能在公開發布前調整；產出報表時從 `seo_pulse_mcp.branding` 讀取 `DISPLAY_NAME` 作為標題、`FOOTER` 作為頁尾。

本 Skill 為待實際掛載驗證的骨架。使用繁體中文，假資料必須明確標示。
1. 以 Asia/Taipei 今天減 3 天為結束日，取最近 7 個完整日及前一週。
2. 呼叫 list_sites、gsc_compare_weeks、ga4_compare_weeks。取得前 4 週資料並計算每週平均 baseline；不可將合計當平均。GSC 保留每日 query/page，避免重複加總不同層級資料。
3. ga4_compare_weeks 已依正式網域白名單清理 GA4；把回傳的 `data_quality.current` 放進 detect_anomalies 的 `current.data_quality`，以保留排除 sessions 數與佔比。超過 20% 標示「資料污染警告」。
4. 呼叫 detect_anomalies(current, previous, rules)，current.baseline 放入前四週平均。缺少 baseline 時明確標示 A1/A2/A8 未評估。
5. 依序輸出：本週摘要（3 句內）、資料品質（排除 sessions 數量與佔比、資料缺漏、A9 網址問題）、依 P0/P1/P2 分組的異常與機會、低流量觀察（未達門檻的原始數字）、下週建議（最多 5 條）。每條建議含頁面／查詢、本週／上週／變化%、可能原因、動作、規則 ID；原因只能列為假設，不自動修改網站。
6. AI 引用：待 01 研究數據
7. 頁尾：Powered by LS-Labs｜MIT
