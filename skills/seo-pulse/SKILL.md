---
name: seo-pulse
description: 查詢網站的 Google Search Console 與 GA4 搜尋流量、比較週對週變化、偵測異常，並產出繁體中文搜尋流量週報時使用。
---

使用繁體中文。所有工具都是唯讀，不會修改網站。`fixture` 為 true 的資料是假資料，回答與週報都要明說。

## 開始前：唯讀驗證
先呼叫 `list_sites`，回報看得到哪些網站；再呼叫 `weekly_report`（不帶參數），回報 `periods` 的本週、上週與 baseline 日期範圍。確認資料來源與期間正確後，再開始其他查詢。

需要指定特定網站或 GA4 資源時：

- `gsc_query`、`gsc_compare_weeks`、`weekly_report` 可傳 `site_url`（例如 `sc-domain:example.com` 或 `https://example.com/`）。
- `ga4_report`、`ga4_compare_weeks`、`weekly_report` 可傳 `property_id`（純數字的 GA4 資源 ID），不知道 ID 時先呼叫 `list_ga4_properties`。
- 這三個 GA4 工具也都能傳 `production_hosts` 覆寫正式網域清單。
- 本機版沒傳時使用伺服器環境變數的預設值。
- 雲端版（例如在 ChatGPT 使用）沒有預設網站：先 `list_sites` 與 `list_ga4_properties`，請使用者確認要看哪個網站與資源，再帶 `site_url` 與 `property_id` 呼叫 `weekly_report`。
- 格式錯誤會回傳清楚的錯誤訊息。

資料品質出現「同網域其他子網域…未計入」時，照實轉述，並問使用者這些子網域是否也是正式站；是的話用 `production_hosts` 重新產生週報。

## 什麼時候查 GSC、什麼時候查 GA4
- GSC（`list_sites`、`gsc_query`、`gsc_compare_weeks`）：搜尋曝光、點擊、排名、查詢字、頁面，也就是 Google 搜尋結果裡發生的事。
- GA4（`ga4_report`、`ga4_compare_weeks`）：進站後的 sessions、key events、流量管道與來源。
- 兩者數字不會相等，規則 A13 就是檢查這個差異；不要把 GSC 點擊當成 GA4 sessions。
- `detect_anomalies` 套用固定規則找異常；`weekly_report` 一次抓齊本週、上週與 baseline 並產出整份週報資料。

## 名次和點擊率怎麼解讀
- position 是曝光加權平均，數字越小越前面；約 1–10 名為第一頁，11–20 為第二頁，規則 A6 把 11–20 視為機會查詢。
- CTR = clicks / impressions，由工具重算，不要自行轉抄或四捨五入。
- CTR 高低要對照同名次的參考值（`seo_pulse_mcp/config/ctr_benchmarks.json`）才有意義，規則 A5 用的就是這份。
- 曝光太少時，排名與 CTR 波動很大，不下結論。
- 名次變好但 CTR 下降，可能是新查詢字帶來的曝光，先看查詢字再判斷。

## 週報流程
1. 呼叫 `weekly_report(format="markdown")`。使用者指定週次時傳 `end_date`（該週最後一天，YYYY-MM-DD）。不要自己抓原始 rows，也不要自己算 baseline。
2. 回傳的 Markdown 就是整份週報，標題與頁尾都已產生。只替換兩段以「> 由 AI」開頭的佔位文字：
   - 「本週摘要」：3 句內。先說全站點擊與曝光的方向與幅度，再說最重要的一到兩個異常，最後一句帶過資料品質。
   - 「下週建議」：最多 5 條。每條依序寫頁面或查詢、本週／上週／變化%、可能原因、動作、規則 ID；依週報的 P0、P1、P2 排序，一條只對應一個異常。
   其餘標題、表格、資料品質與頁尾原樣保留，數字一個都不能改。
3. 需要細節再查：`weekly_report()`（JSON）看完整 findings，`gsc_query` 追單一頁面或查詢，`ga4_compare_weeks` 看管道與來源。

## 寫作規則
- 數字只能來自版面上的表格。變化欄顯示「上週無資料」就照寫，不推算、不補值、不改寫成另一個數。
- 原因一律寫成假設（「可能是」「值得確認」），不下定論，不建議自動修改網站。
- 「資料品質」列出的警告與未評估規則，摘要一定要提到；未評估的規則不可寫成「已檢查無異常」。
- 版面含「以下為假資料示範」時保留該句。
- 建議的依據只有兩種：這份週報表格裡的數字，以及 `docs/rules.md` 的規則定義。不引用產業報告、不寫「研究顯示」、不引用任何外部統計或 LS-Labs 的研究結論。需要外部脈絡時，寫成「建議查證」的待辦，不寫成事實。
- 全站點擊很少時（例如低於 20），明說樣本太小、週對週變化不具意義，建議只寫觀察、不寫動作。

## 不要做的事
- 不替使用者決定門檻。門檻定義在 `docs/rules.md`，要調整請使用者傳 `rules` 參數。
- 不產生第二份版面、不改標題、不在頁尾以外加署名。
- 不用原始 rows 自行加總後取代 `weekly_report` 的數字。
