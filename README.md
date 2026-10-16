# LS-Labs Reports

Python ≥ 3.10 的本機繁中行銷週報 MCP 骨架，MIT 授權。預設只讀取隨套件附上的 **lslabs.tw 風格假資料**（2026-09-28 至 2026-10-11），沒有真實 OAuth 或任何 Google 網路呼叫。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m lslabs_reports.server
```

使用官方 `mcp` Python SDK FastMCP，以 stdio 啟動。若 SDK 無法安裝，工具函式仍可匯入使用，但啟動伺服器會提示安裝 SDK。

Claude Desktop 的 MCP 設定範例（將絕對路徑換成此 app/ 所在位置，重新啟動 Claude）：

```json
{
  "mcpServers": {
    "lslabs-reports": {
      "command": "/absolute/path/app/.venv/bin/python",
      "args": ["-m", "lslabs_reports.server"],
      "cwd": "/absolute/path/app",
      "env": {
        "PYTHONPATH": "/absolute/path/app",
        "LSLABS_CONNECTOR": "fixture",
        "LSLABS_PRODUCTION_HOSTS": "lslabs.tw",
        "LSLABS_EXCLUDE_HOSTS": "test.lslabs.tw"
      }
    }
  }
}
```

工具：`list_sites`、`gsc_query(start_date,end_date,dimensions,filters)`、`gsc_compare_weeks(end_date,dimensions,filters)`、`ga4_report(start_date,end_date)`、`ga4_compare_weeks(end_date)`、`detect_anomalies(current,previous,rules)`。日期為 ISO 格式且包含起訖日；比較工具取結束日起 7 天及前 7 天。週報結束日請以使用者時區（預設 Asia/Taipei）的今天減 3 天計算。GSC 維度支援 date/query/page、filters 為等值字典；排名以曝光加權，CTR 由點擊／曝光重算。

`LSLABS_CONNECTOR=fixture|google` 切換連接器；google 僅為會拋出 NotImplementedError 的 stub。未來 OAuth 只允許 `webmasters.readonly` 與 `analytics.readonly`。尚未實作 OAuth：日後需在 Google Cloud 設定同意畫面、建立使用者自己的 Desktop OAuth 憑證，將應用改為 **In production**，避免外部測試模式的 refresh token 7 天到期。憑證與 token 不可提交版本控制。

GA4 先依 `LSLABS_PRODUCTION_HOSTS`（逗號分隔，預設 lslabs.tw）白名單清理；localhost、127.0.0.1 與 `LSLABS_EXCLUDE_HOSTS` 永遠排除。其他主機（含預覽站）一律排除。`clean_hosts` 回傳排除 sessions、比例及 >20% 污染警告；分析結果亦附此資料。正式主機採完整名稱匹配，不接受萬用字元。

異常依 `../growth/weekly-report-template.md` 的 A1–A14 與 P0/P1/P2。`rules.py` 集中門檻，`rules` 參數可覆寫 minimums、thresholds 等設定。輸入格式如下（數字為示意）：

```python
current = {
    "gsc": [{"date": "2026-10-11", "query": "範例", "page": "https://lslabs.tw/",
             "clicks": 10, "impressions": 100, "position": 8}],
    "ga4": [{"date": "2026-10-11", "hostName": "lslabs.tw", "sessions": 20,
             "keyEvents": 1, "sessionDefaultChannelGroup": "Organic Search",
             "sessionSource": "google"}],
    "baseline": {"gsc": []}  # 前四週每週平均，不是合計；空陣列表示已知無曝光
}
```

previous 同樣含 gsc/ga4；若缺少 baseline，A1/A2/A8 不評估。資料應取同一層級的每日 query/page 明細，勿混入已加總的全站列。A14 只判定前後日都有資料的中間缺漏日。A13 差異定義為 abs(GSC clicks − Google Organic sessions) / GSC clicks。GA4 異常分數依範本採全站 clicks 差值、無 clicks 時採 impressions/10；前 2 名依技術／資料置頂後的排序判定。缺少資料時不可宣稱已完整驗證所有規則。

CTR 暫定值位於 `lslabs_reports/config/ctr_benchmarks.json`，可用 `LSLABS_CTR_BENCHMARKS_PATH` 或 `rules.ctr_benchmarks_path` 指向同格式 JSON，也可傳 `rules.expected_ctr_by_position`。這些值不是產業引用，累積 **4 週真實資料後須替換**為本站歷史中位數。

`skill/SKILL.md` 是繁中週報流程骨架，仍需在 Claude 實際掛載驗證；AI 引用固定為「待 01 研究數據」。尚未驗證真實資料、OAuth 或發布流程，程式不修改網站。

由 LS-Labs 製作
