# LS-Labs SEO Pulse 流量脈搏

不改任何東西：先呼叫 `list_sites`，回報你看得到哪些網站；再呼叫 `weekly_report`（不帶參數），回報回傳的 `periods` 裡本週、上週與 baseline 各涵蓋哪些日期。若 `fixture` 為 true，請註明是假資料。

**用你自己的 Google Search Console 和 GA4 資料，讓 AI 每週幫你寫繁中搜尋流量週報。**

SEO Pulse 是一個在你電腦上執行的 MCP 伺服器，加上一份繁中週報 Skill。接上 Claude Code、Claude Desktop 或其他支援 MCP 的 AI 工具之後，AI 會讀取你網站最近兩週的 GSC 與 GA4 數據，比較週對週變化，用固定規則找出異常，再寫成一份有摘要、異常和建議優先序的週報。

- **你的資料留在你手上**：使用你自己建立的 Google OAuth 憑證，只申請 `webmasters.readonly` 和 `analytics.readonly` 兩個唯讀權限，token 存在你的電腦，不經過我們的伺服器。
- **推理用你自己的 AI**：週報由你已經在用的 AI 撰寫，工具本身不呼叫任何模型 API。目前實際驗證過 Claude Code 與 Claude Desktop；Codex、Cursor 只驗過設定格式。
- **異常判斷看得懂、測得到**：14 條異常規則（例如點擊驟降、排名掉出前 10、資料缺漏日）都是確定性計算，附單元測試，門檻可以自己覆寫。
- **小站也不誤報**：每條規則都有最低流量門檻；GA4 會先排除 localhost 和測試網域的流量再計算。

顯示名稱可能在公開發布前調整；程式以 `seo_pulse_mcp/branding.py` 的 `DISPLAY_NAME` 與 `FOOTER` 為準。

## 安裝

### 方式一：Plugin（Claude Code）

只需先安裝 [uv](https://docs.astral.sh/uv/)：macOS／Linux 執行 `curl -LsSf https://astral.sh/uv/install.sh | sh`，Windows 執行 `winget install astral-sh.uv`。Python 與套件由 uv 依 `uv.lock` 建在 plugin 自己的隔離環境，不碰你系統的 Python，也不用手動 pip install。

```bash
claude plugin marketplace add Wenqing950519/lslabs-seo-pulse
claude plugin install seo-pulse@lslabs-seo-pulse
```

也可以先 clone 再用本機路徑：`claude plugin marketplace add /absolute/path/to/lslabs-seo-pulse`。第一次啟動會下載依賴，約需數十秒。Windows、macOS、Linux 走同一套設定，Windows 11 已實測連線成功。

另附 Codex（`.codex-plugin/plugin.json`）與 Cursor（`.cursor-plugin/plugin.json`）manifest，啟動方式相同，目前只驗證過格式，尚未實際掛載測試。

### 方式二：pip install（備援）

照下方「安裝與測試」的 venv／pip 步驟安裝，再依「掛載到 Claude」的 Claude Desktop MCP JSON 或 `claude mcp add` 設定。

## 版本與更新

不自動更新；工具描述有任何改變都會換新版本號，指紋見 tool-contract.json。

- 不會自動下載任何東西。要確認是否有新版，請開啟 GitHub master 上的 [`tool-contract.json`](https://github.com/Wenqing950519/lslabs-seo-pulse/blob/master/tool-contract.json)，比對 `version` 與 `fingerprint` 和你本機的副本。
- 若不同，先看變更紀錄，再手動更新：從本機資料夾安裝的不用重裝，`git pull` 後重新開啟 session 即生效；從 GitHub 加入 marketplace 的，要先執行 `claude plugin marketplace update lslabs-seo-pulse`，再執行 `claude plugin update seo-pulse@lslabs-seo-pulse`。
- 升級 `mcp` 或 `pydantic` 之後，若 `tool-contract.json` 的指紋改變，也算一次版本變更，要換新版本號。
- `.venv/bin/python scripts/generate_tool_contract.py --check` 可驗證本機伺服器是否與自己的合約一致。

## 安裝與測試

macOS／Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test,google]'
.venv/bin/python -m pytest -q
```

Windows（PowerShell）：

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test,google]"
.venv\Scripts\python.exe -m pytest -q
```

只用假資料試用時可改裝 `.[test]`；Google 相關測試會自動跳過。Windows 會一併安裝 `tzdata`，讓 `Asia/Taipei` 等時區可用。

使用官方 `mcp` Python SDK FastMCP，以 stdio 啟動：`python -m seo_pulse_mcp.server`。

## 掛載到 Claude

Claude Desktop：編輯設定檔（Windows 為 `%APPDATA%\Claude\claude_desktop_config.json`，macOS 為 `~/Library/Application Support/Claude/claude_desktop_config.json`），把路徑換成此 repo 的絕對路徑後重新啟動 Claude。Windows 範例：

```json
{
  "mcpServers": {
    "seo-pulse": {
      "command": "C:\\path\\to\\seo-pulse\\.venv\\Scripts\\python.exe",
      "args": ["-m", "seo_pulse_mcp.server"],
      "env": {
        "SEO_PULSE_CONNECTOR": "fixture",
        "SEO_PULSE_PRODUCTION_HOSTS": "example.com",
        "SEO_PULSE_EXCLUDE_HOSTS": "staging.example.com"
      }
    }
  }
}
```

macOS／Linux 的 `command` 改為 `/path/to/seo-pulse/.venv/bin/python`。套件以 `pip install -e` 安裝，不需另設 `PYTHONPATH` 或 `cwd`。

Claude Code：

```bash
claude mcp add seo-pulse -e SEO_PULSE_CONNECTOR=fixture -- /path/to/seo-pulse/.venv/bin/python -m seo_pulse_mcp.server
```

Windows 把最後的路徑換成 `C:\path\to\seo-pulse\.venv\Scripts\python.exe`。週報流程見 `skill/SKILL.md`，可放進 Claude 的 Skills 使用。

## 工具

主要工具：`weekly_report(end_date=None, top_n=20, format="json")`。`format="markdown"` 時回傳排好版的繁中週報：標題、期間、關鍵數字、資料品質、依 P0/P1/P2 分組的異常、熱門頁面與查詢都由程式產生，AI 只替換「本週摘要」與「下週建議」兩段的佔位文字，數字不經 AI 轉抄。JSON 模式由伺服器端一次抓取本週、上週（GSC 含每日 date/query/page）與前四週 baseline，GA4 只清理一次並保留資料品質，套用 A1–A14 後只回傳精簡結果：`periods`、`totals`（GSC／GA4 本週、上週、變化%、baseline 週平均）、`data_quality`、`top_pages`／`top_queries`、依優先序排序的 `findings`（最多 `top_n` 筆，`findings_total` 為總數）、`priority_counts`、`not_evaluated` 與 `warnings`。`end_date` 省略時以 `SEO_PULSE_TIMEZONE` 的今天減 `SEO_PULSE_GSC_LAG_DAYS` 天計算。baseline 為本週之前四週（含上週）的每週平均；有資料的天數不足 28 天、本週資料不足 7 天或 GA4 污染超過 20% 時列入 `warnings`。

追查用工具：`list_sites`、`gsc_query(start_date,end_date,dimensions,filters)`、`gsc_compare_weeks(end_date,dimensions,filters)`、`ga4_report(start_date,end_date)`、`ga4_compare_weeks(end_date)`、`detect_anomalies(current,previous,rules)`。日期為 ISO 格式且包含起訖日；比較工具取結束日起 7 天及前 7 天。GSC 維度支援 date/query/page、filters 為等值字典；排名以曝光加權，CTR 由點擊／曝光重算。這些工具回傳原始 rows，資料量大時請改用 `weekly_report`。

設定集中於 `seo_pulse_mcp/settings.py`，全部由環境變數讀取：

| 變數 | 預設 | 用途 |
|---|---|---|
| `SEO_PULSE_CONNECTOR` | `fixture` | `fixture` 或 `google` |
| `SEO_PULSE_PRODUCTION_HOSTS` | `example.com` | GA4 正式網域白名單，逗號分隔；Google 模式必須設定 |
| `SEO_PULSE_EXCLUDE_HOSTS` | 空 | 額外排除的主機 |
| `SEO_PULSE_CANONICAL_ORIGIN` | `https://` + 第一個正式主機 | A9 正式網址 |
| `SEO_PULSE_TIMEZONE` | `Asia/Taipei` | 預設結束日的時區（IANA 名稱） |
| `SEO_PULSE_GSC_LAG_DAYS` | `3` | GSC 資料延遲天數 |
| `SEO_PULSE_CTR_BENCHMARKS_PATH` | 內建 JSON | A5 預期 CTR |

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

GA4 先依 `SEO_PULSE_PRODUCTION_HOSTS`（逗號分隔，預設 example.com）白名單清理；localhost、127.0.0.1 與 `SEO_PULSE_EXCLUDE_HOSTS` 永遠排除。其他主機（含預覽站）一律排除。`clean_hosts` 回傳排除 sessions、比例及 >20% 污染警告；分析結果亦附此資料。正式主機採完整名稱匹配，不接受萬用字元，逗號後的空白會忽略。

A9 以 `SEO_PULSE_CANONICAL_ORIGIN`（例如 `https://lslabs.tw`）判定正式網址；未設定時取 `https://` 加第一個正式主機。scheme 或主機不同的 GSC 網址（含 www 變體）才列為 A9。

異常規則 A1–A14 與 P0/P1/P2 的定義見 [`docs/rules.md`](docs/rules.md)。`rules.py` 集中門檻，`rules` 參數可覆寫 minimums、thresholds 等設定。輸入格式如下（數字為示意）：

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

使用 `ga4_compare_weeks` 的已清理 rows 時，請把其 `data_quality.current` 放進 `current.data_quality`，否則排除比例會以已清理資料重算為 0。previous 同樣含 gsc/ga4；若缺少 baseline，A1/A2/A8 不評估。資料應取同一層級的每日 query/page 明細，勿混入已加總的全站列。A14 只判定前後日都有資料的中間缺漏日。A13 差異定義為 abs(GSC clicks − Google Organic sessions) / GSC clicks。GA4 異常分數依範本採全站 clicks 差值、無 clicks 時採 impressions/10；前 2 名依技術／資料置頂後的排序判定。缺少資料時不可宣稱已完整驗證所有規則。

CTR 暫定值位於 `seo_pulse_mcp/config/ctr_benchmarks.json`，可用 `SEO_PULSE_CTR_BENCHMARKS_PATH` 或 `rules.ctr_benchmarks_path` 指向同格式 JSON，也可傳 `rules.expected_ctr_by_position`。這些值不是產業引用，累積 **4 週真實資料後須替換**為本站歷史中位數。

`skill/SKILL.md` 與 `skills/seo-pulse/SKILL.md` 是繁中週報流程；AI 引用目前固定為「待 01 研究數據」，待對應研究完成後替換。2026-10-21 已用 LS-Labs 自有網站的真實 GSC／GA4 資料與 Desktop OAuth 驗證過 `weekly_report`；Codex、Cursor 的實際掛載與對外發布流程尚未驗證。程式不修改網站。

---
免費、開源（MIT）。由 LS-Labs 製作。
