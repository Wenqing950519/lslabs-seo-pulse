---
name: seo-pulse
description: 查詢網站的 Google Search Console 與 GA4 搜尋流量、比較週對週變化、偵測異常，並產出繁體中文搜尋流量週報時使用。
---

使用繁體中文。所有工具都是唯讀，不會修改網站；假資料必須明確標示。

## 開始前：唯讀驗證
先呼叫 `list_sites`，回報看得到哪些網站；再呼叫 `weekly_report`（不帶參數），回報 `periods` 的本週、上週與 baseline 日期範圍（`fixture` 為 true 時註明是假資料），再開始其他查詢。

## 什麼時候查 GSC、什麼時候查 GA4
- GSC（`list_sites`、`gsc_query`、`gsc_compare_weeks`）：搜尋曝光、點擊、排名、查詢字、頁面，也就是 Google 搜尋結果裡發生的事。
- GA4（`ga4_report`、`ga4_compare_weeks`）：進站後的 sessions、key events、流量管道與來源。
- 兩者數字不會相等（規則 A13 就是檢查這個差異），不要把 GSC 點擊直接當成 GA4 sessions。
- `detect_anomalies` 套用固定規則找異常；`weekly_report` 一次產出整份週報資料。

## 名次和點擊率怎麼解讀
- position 是曝光加權平均，數字越小越前面；約 1–10 名為第一頁，11–20 為第二頁，11–30 視為「接近前 10」。
- CTR = clicks / impressions，由工具重算，不要自行轉抄。
- CTR 要對照同名次的期望值（`seo_pulse_mcp/config/ctr_benchmarks.json`，暫定值）才能判斷高低。
- 曝光太少時，排名與 CTR 波動很大，不下結論。
- 名次變好但 CTR 下降，可能是新查詢字帶來的曝光，先看查詢字再判斷。

## 週報流程
週報標題與頁尾由 `weekly_report` 的 Markdown 版面產生，不需另外撰寫。
1. 呼叫 `weekly_report(format="markdown")`；使用者指定週次時傳 `end_date`（該週最後一天，YYYY-MM-DD）。不要自行抓原始 rows 或自行計算 baseline。
2. 回傳的 Markdown 就是週報版面。只替換兩段以「> 由 AI」開頭的佔位文字：「本週摘要」（3 句內）與「下週建議」（最多 5 條，每條含頁面／查詢、本週／上週／變化%、可能原因、動作、規則 ID）。其餘標題、表格、資料品質與頁尾原樣保留，不可改動數字。
3. 數字只引用版面中的表格；變化顯示「上週無資料」時照寫，不可自行推算或補值。原因只能寫成假設，不自動修改網站。
4. 「資料品質」列出的警告與未評估規則必須在摘要中提及；未評估的規則不可宣稱已檢查。版面含「以下為假資料示範」時不可刪除。
5. 需要細節時，再用 `weekly_report()`（JSON）或 `gsc_query` 追查單一頁面或查詢。
6. AI 引用：待 01 研究數據
