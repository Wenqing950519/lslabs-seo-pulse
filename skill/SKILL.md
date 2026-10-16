---
name: seo-pulse-weekly-report
description: LS-Labs SEO Pulse 流量脈搏繁中行銷週報骨架，以本機 MCP 的 GSC／GA4 資料產出週報建議。
---

週報標題：LS-Labs SEO Pulse 流量脈搏。顯示名稱可能在公開發布前調整；產出報表時從 `seo_pulse_mcp.branding` 讀取 `DISPLAY_NAME` 作為標題、`FOOTER` 作為頁尾。

本 Skill 為待實際掛載驗證的骨架。使用繁體中文，假資料必須明確標示。
1. 呼叫 `weekly_report()`；使用者指定週次時傳 `end_date`（該週最後一天，YYYY-MM-DD）。不要自行抓原始 rows 或自行計算 baseline。
2. `fixture` 為 true 時，標題下方標示「以下為假資料示範」。
3. 數字只引用回傳的 `totals`、`top_pages`、`top_queries`、`findings`，不可自行推算或補值；變化%為 null 時寫「上週無資料」。
4. `warnings` 與 `not_evaluated` 必須原樣列在「資料品質」段落，未評估的規則不可宣稱已檢查。
5. 依序輸出：本週摘要（3 句內）、資料品質（GA4 排除 sessions 數與佔比、資料缺漏、A9 網址問題）、依 P0/P1/P2 分組的異常與機會、低流量觀察（top_pages／top_queries 中未觸發規則但變化明顯的項目）、下週建議（最多 5 條）。每條建議含頁面／查詢、本週／上週／變化%、可能原因、動作、規則 ID；原因只能列為假設，不自動修改網站。需要細節時再用 `gsc_query` 追查單一頁面或查詢。
6. AI 引用：待 01 研究數據
7. 頁尾：Powered by LS-Labs｜MIT
