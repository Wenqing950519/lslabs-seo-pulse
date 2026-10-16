# LS-Labs SEO Pulse 流量脈搏

**用你自己的 Google Search Console 和 GA4 資料，讓 AI 每週幫你寫繁中搜尋流量週報。**

SEO Pulse 是一個在你電腦上執行的 MCP 伺服器，加上一份繁中週報 Skill。接上 Claude 或 ChatGPT 之後，AI 會讀取你網站最近兩週的 GSC 與 GA4 數據，比較週對週變化，用固定規則找出異常，再寫成一份有摘要、異常和建議優先序的週報。

- **你的資料留在你手上**：使用你自己建立的 Google OAuth 憑證，只申請 `webmasters.readonly` 和 `analytics.readonly` 兩個唯讀權限，token 存在你的電腦，不經過我們的伺服器。
- **推理用你自己的 AI**：週報由你已經在用的 Claude 或 ChatGPT 撰寫，工具本身不呼叫任何模型 API。<!-- TODO: ChatGPT 掛載方式驗收後再寫 -->
- **異常判斷看得懂、測得到**：14 條異常規則（例如點擊驟降、排名掉出前 10、資料缺漏日）都是確定性計算，附單元測試，門檻可以自己覆寫。
- **小站也不誤報**：每條規則都有最低流量門檻；GA4 會先排除 localhost 和測試網域的流量再計算。

顯示名稱可能在公開發布前調整；程式以 `seo_pulse_mcp/branding.py` 的 `DISPLAY_NAME` 與 `FOOTER` 為準。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test,google]'
.venv/bin/python -m pytest -q
.venv/bin/python -m seo_pulse_mcp.server
```

使用官方 `mcp` Python SDK FastMCP，以 stdio 啟動。若 SDK 無法安裝，工具函式仍可匯入使用，但啟動伺服器會提示安裝 SDK。

Claude Desktop 的 MCP 設定範例（將絕對路徑換成此 app/ 所在位置，重新啟動 Claude）：

```json
{
  "mcpServers": {
    "seo-pulse": {
      "command": "/absolute/path/app/.venv/bin/python",
      "args": ["-m", "seo_pulse_mcp.server"],
      "cwd": "/absolute/path/app",
      "env": {
        "PYTHONPATH": "/absolute/path/app",
        "SEO_PULSE_CONNECTOR": "fixture",
        "SEO_PULSE_PRODUCTION_HOSTS": "example.com",
        "SEO_PULSE_EXCLUDE_HOSTS": "staging.example.com"
      }
    }
  }
}
```

工具：`list_sites`、`gsc_query(start_date,end_date,dimensions,filters)`、`gsc_compare_weeks(end_date,dimensions,filters)`、`ga4_report(start_date,end_date)`、`ga4_compare_weeks(end_date)`、`detect_anomalies(current,previous,rules)`。日期為 ISO 格式且包含起訖日；比較工具取結束日起 7 天及前 7 天。週報結束日請以使用者時區（預設 Asia/Taipei）的今天減 3 天計算。GSC 維度支援 date/query/page、filters 為等值字典；排名以曝光加權，CTR 由點擊／曝光重算。

`SEO_PULSE_CONNECTOR=fixture|google` 切換連接器。Google 連接器為自行撰寫的薄層，僅使用 GSC `https://www.googleapis.com/auth/webmasters.readonly` 與 GA4 `https://www.googleapis.com/auth/analytics.readonly`，各自授權與快取。

Google 設定步驟：

1. 建立自己的 Google Cloud (GCP) 專案，啟用 **Search Console API** 及 **Google Analytics Data API**。
2. 設定 OAuth 同意畫面；外部應用在測試階段先加入自己的 Google 帳號為測試使用者。
3. 建立 OAuth 用戶端，應用程式類型選 **Desktop app／電腦版應用程式**。下載 client_secret JSON 至 repo 外，例如 `~/.config/seo-pulse/client_secret.json`。
4. 安裝 Google 選用依賴：`.venv/bin/python -m pip install -e '.[google]'`，設定以下環境變數。
5. 執行 `.venv/bin/seo-pulse auth`（或 `.venv/bin/python -m seo_pulse_mcp.server auth`），依序完成 GSC、GA4 瀏覽器授權。工具不會自行開啟登入流程；授權失效會提示重新執行 auth。
6. 將 OAuth 應用發布狀態切換為 **「正式版 / In production」**，避免外部應用 Testing 模式下 refresh token 7 天到期。個人自用且尚未通過 Google 驗證的應用可能顯示「未經驗證的應用程式」警告；確認是自己建立的專案與唯讀權限後才繼續。

```bash
export SEO_PULSE_GOOGLE_CLIENT_SECRET="$HOME/.config/seo-pulse/client_secret.json"
export SEO_PULSE_TOKEN_DIR="$HOME/.config/seo-pulse/tokens"
export SEO_PULSE_GSC_SITE_URL="sc-domain:example.com"  # 或 Search Console 中完整 URL-prefix
export SEO_PULSE_GA4_PROPERTY_ID="123456789"  # 數字資源 ID，不是 G- 開頭的評估 ID
export SEO_PULSE_CONNECTOR="google"
.venv/bin/seo-pulse auth
.venv/bin/seo-pulse
```

MCP 設定中的 env 也須填入以上變數（使用絕對路徑），並將 `SEO_PULSE_CONNECTOR` 改為 `google`。帳號須已有對應 GSC 屬性及 GA4 資源的讀取權限。token 預設放在 repo 外的 `~/.config/seo-pulse/tokens/`，檔案僅擁有者可讀寫；`SEO_PULSE_TOKEN_DIR` 可覆寫位置。勿將憑證或 token 放入 repo；`.gitignore` 已排除 `tokens/` 與 `client_secret*.json`。有效 token 自動沿用，過期且可刷新時自動更新。

GA4 先依 `SEO_PULSE_PRODUCTION_HOSTS`（逗號分隔，預設 example.com）白名單清理；localhost、127.0.0.1 與 `SEO_PULSE_EXCLUDE_HOSTS` 永遠排除。其他主機（含預覽站）一律排除。`clean_hosts` 回傳排除 sessions、比例及 >20% 污染警告；分析結果亦附此資料。正式主機採完整名稱匹配，不接受萬用字元。

異常依 `../growth/weekly-report-template.md` 的 A1–A14 與 P0/P1/P2。`rules.py` 集中門檻，`rules` 參數可覆寫 minimums、thresholds 等設定。輸入格式如下（數字為示意）：

```python
current = {
    "gsc": [{"date": "2026-10-11", "query": "範例", "page": "https://example.com/",
             "clicks": 10, "impressions": 100, "position": 8}],
    "ga4": [{"date": "2026-10-11", "hostName": "example.com", "sessions": 20,
             "keyEvents": 1, "sessionDefaultChannelGroup": "Organic Search",
             "sessionSource": "google"}],
    "baseline": {"gsc": []}  # 前四週每週平均，不是合計；空陣列表示已知無曝光
}
```

previous 同樣含 gsc/ga4；若缺少 baseline，A1/A2/A8 不評估。資料應取同一層級的每日 query/page 明細，勿混入已加總的全站列。A14 只判定前後日都有資料的中間缺漏日。A13 差異定義為 abs(GSC clicks − Google Organic sessions) / GSC clicks。GA4 異常分數依範本採全站 clicks 差值、無 clicks 時採 impressions/10；前 2 名依技術／資料置頂後的排序判定。缺少資料時不可宣稱已完整驗證所有規則。

CTR 暫定值位於 `seo_pulse_mcp/config/ctr_benchmarks.json`，可用 `SEO_PULSE_CTR_BENCHMARKS_PATH` 或 `rules.ctr_benchmarks_path` 指向同格式 JSON，也可傳 `rules.expected_ctr_by_position`。這些值不是產業引用，累積 **4 週真實資料後須替換**為本站歷史中位數。

`skill/SKILL.md` 是繁中週報流程骨架，仍需在 Claude 實際掛載驗證；AI 引用固定為「待 01 研究數據」。尚未驗證真實資料、OAuth 或發布流程，程式不修改網站。

---
免費、開源（MIT）。由 LS-Labs 製作。
