# 2026-10-16

於 app/ 內建立 Python SEO Pulse 流量脈搏 MVP 骨架：FastMCP stdio 工具、可切換的 fixture／Google stub 連接器、兩週假資料、正式網域清理、A1–A14 確定性規則及分析師 P0/P1/P2 計分。CTR 保留可覆寫的暫定值。補上繁中 README、週報 Skill 骨架、MIT 與測試。

尚未串接 OAuth、Google 真實資料、Claude 實際掛載或對外發布；AI 引用為「待 01 研究數據」。

驗證：Python compileall 通過；以獨立無依賴檢查執行 78 個測試案例的斷言皆通過（不是 pytest）。已嘗試 pip 預設索引、PyPI 與環境代理，分別受 DNS／連線權限阻擋；環境沒有可用 pytest 或 mcp。指定命令 `.venv/bin/python -m pytest -q` 的最終結果為 `No module named pytest`，尚不能宣稱 pytest 全綠。官方 SDK 安裝後可直接啟用 FastMCP；未安裝時不提供替代 MCP 協定。

UPDATE 2：補齊 credentials*.json、service-account*.json、tokens、node_modules、run*.log、last.txt 忽略規則；未 commit。

# 2026-10-16（repo 拉到 Windows 本機後）

- Windows 相容：所有文字讀寫指定 UTF-8；token 0600 權限檢查只在 POSIX 執行。
- 修正真實網站會遇到的 4 個 bug：主機清單逗號後空白、A9 正式網址寫死 example.com、`data_quality` 在 `detect_anomalies` 被重算為 0、未安裝 Google 套件時 fixture 模式無法啟動。
- 新增 `settings.py` 集中讀取 SEO_PULSE_* 設定，以及伺服器端 `weekly_report`：一次抓取本週、上週與前四週 baseline，只回傳精簡結果。
- `weekly_report(format="markdown")` 由程式產生週報版面，AI 只撰寫摘要與建議；規則說明正本移到 `docs/rules.md`；README 補 Windows 與 Claude 掛載說明。

驗證：pytest 全數通過（完整安裝；只裝 `.[test]` 時 Google 測試跳過）；以 MCP stdio 用戶端實際呼叫 `weekly_report` 的 JSON 與 Markdown 兩種格式。尚未驗證真實 Google 資料、OAuth 與 Claude Desktop 實際掛載。

# 2026-10-18 Plugin 打包＋工具描述固定版本（tool contract）

分支 `feat/plugin-tool-contract`（從 origin/master f756400 開出），已推送到 GitHub，並開 PR #1（https://github.com/Wenqing950519/lslabs-seo-pulse/pull/1），尚未合併；repo 維持 private，沒有上架或發布。規格：`projects/ls-labs-reports/handoffs/2026-10-18-plugin-and-tool-contract.md`。

## 改了什麼
- **Plugin 打包**（repo 根目錄就是 plugin 根目錄）：
  - `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`（Claude Code 官方格式，`claude plugin validate` 通過；marketplace 只有一個「未填 marketplace 描述」的警告）。
  - `.codex-plugin/plugin.json`（Codex 官方相容格式，對照 OpenAI 文件的欄位規格）。
  - `.cursor-plugin/plugin.json`（Cursor 官方格式，以 cursor/plugins 的 JSON Schema 驗證通過）。
  - `.mcp.json`：三家共用，啟動指令沿用現有 server：`python3 -m seo_pulse_mcp.server`，`PYTHONPATH=${CLAUDE_PLUGIN_ROOT}`。沒有寫死 `SEO_PULSE_CONNECTOR`，預設 fixture，使用者自己的環境變數照常生效。
  - 新增總 Skill `skills/seo-pulse/SKILL.md`：以 `skill/SKILL.md` 的週報流程為基礎，補上「什麼時候查 GSC、什麼時候查 GA4」與「名次和點擊率怎麼解讀」，開頭先做 `list_sites` 唯讀驗證。原本的 `skill/SKILL.md` 不動。
- **工具描述固定版本**：
  - `scripts/generate_tool_contract.py`：從 server 實際註冊的工具（FastMCP `list_tools()`）產生 `tool-contract.json`，記錄版本號（取自 pyproject.toml）、每個工具的名稱、描述、input schema 與各自的 SHA-256，加上整體指紋。沒有官方 mcp SDK 時直接報錯，不會改用手寫資料。工具改了但版本號沒換時，產生腳本拒絕覆寫；`--check` 只比對不寫檔。
  - `tool-contract.json`：版本 0.1.0，7 個工具，指紋 `b16882200156ddb2e2960b06ed0433e8d4b4e87737c18fb4e1e706e2130592d3`。
  - `tests/test_tool_contract.py`（5 個測試）：實際工具與 contract 不一致就 fail，訊息提醒換版本號；另外檢查檔內雜湊沒被手改、pyproject 與三份 plugin.json 版本一致、manifest 路徑存在。
- **README**：最上面加唯讀驗證句；新增「安裝」（方式一 Plugin、方式二 pip install 備援）與「版本與更新」（不自動更新、手動比對 GitHub 上的 tool-contract.json，不自動下載）。
- 沒改任何工具的行為、描述或 Google 連線邏輯；pyproject.toml 版本維持 0.1.0。

## 使用者會注意到什麼
- 可以用 Claude Code 直接從本機路徑安裝：`claude plugin marketplace add <repo 路徑>`，再 `claude plugin install seo-pulse@lslabs-seo-pulse`。前提是 PATH 上的 `python3` 已安裝 `mcp>=1,<2`。
- 舊的 pip install＋手動 MCP 設定照樣能用。
- 每次工具描述改變都會換版本號；要不要更新由使用者自己決定，plugin 不會自動更新。

## 驗證
- `.venv/bin/python -m pytest -q`：119 passed（原本 114，加上 5 個 contract 測試）。
- `scripts/generate_tool_contract.py --check`：一致。
- 故意把 `list_sites` 的描述改掉：contract 測試 fail，訊息指出「list_sites 的 description 不同」並提醒換版本號；產生腳本也拒絕在版本號不變的情況下覆寫。還原後 119 passed。
- Claude Code v2.1.299：在暫存專案以 local scope 從本機路徑加入 marketplace 並安裝 plugin，`claude mcp list` 顯示 `plugin:seo-pulse:seo-pulse ✔ Connected`；用 fixture 資料呼叫 `list_sites` 成功，回傳 `https://example.com/`（fake: true）。測完已移除這個本機安裝。
- Codex、Cursor：只驗證格式，沒有實際掛載測試。

## 已知限制
- Codex 是否會展開 `.mcp.json` 裡的 `${CLAUDE_PLUGIN_ROOT}`，官方文件沒寫（文件只說 hook 會拿到 `CLAUDE_PLUGIN_ROOT`）。沒展開的話，需要先 pip install 套件才能啟動。Cursor 文件寫明會展開 `${CLAUDE_PLUGIN_ROOT}`。
- Windows 上可能沒有 `python3` 指令，README 請 Windows 使用者改用 pip 方式。
- `list_sites` 只回傳網站清單，不含日期範圍；這次規格不改工具行為，所以唯讀驗證句裡的「日期範圍」要靠其他工具補。
- input schema 是由 mcp／pydantic 自動產生，日後升級這兩個套件可能讓 schema 雜湊改變，contract 測試會 fail；這時照提示換版本號重新產生即可。

# 2026-10-19 PR #1 驗收修正
依 `projects/ls-labs-reports/engineering/2026-10-19-pr1-acceptance-review.md`，在同一個 PR 補一個小 commit：
- README／總 Skill 的唯讀驗證句改為先 `list_sites`，再用不帶參數的 `weekly_report` 回報 `periods`（`list_sites` 不會回傳日期範圍）。
- 新增 Codex 專用 `.codex-mcp.json`（不設 env，`cwd: "."`），`.codex-plugin/plugin.json` 改指向它；Claude／Cursor 共用的 `.mcp.json` 不變。Codex 仍只驗證格式。
- 指紋測試改為直接 `import mcp`，缺依賴時報錯，不再靜默跳過。
- README 更新說明改寫（本機資料夾安裝免重裝；GitHub marketplace 要先 marketplace update 再 plugin update），並補「升級 mcp／pydantic 後指紋改變也要換版本號」。
- `.claude-plugin/marketplace.json` 補最外層 `description`，`claude plugin validate --strict` 通過。
- 工具未改動，`tool-contract.json` 不需重新產生，版本維持 0.1.0。

# 2026-10-21 Plugin 改用 uv 啟動；真實資料驗證；v0.1.0

- 問題：`.mcp.json` 用裸 `python3` 啟動。Windows 的 PATH 上 `python3` 通常是 Microsoft Store 空殼，plugin 裝完連不上；而且使用者得先手動在系統 Python 裝 mcp 與 Google 套件。
- 修正：`.mcp.json`、`.codex-mcp.json` 改為 `uv run --project <root> --extra google --quiet python -m seo_pulse_mcp.server`，並提交 `uv.lock`（65 個套件）。uv 在 plugin 目錄建立隔離環境，不碰系統 Python，使用者只需先裝 uv。新增 `tests/test_plugin_launch.py` 鎖住「不得裸用 python3」與「uv.lock 必須提交」；`test_tool_contract.py` 的 args 斷言改為只看入口模組。
- 工具未改動，`tool-contract.json` 指紋不變；版本維持 0.1.0，打 `v0.1.0` 標籤作為第一個公開版本。
- README：安裝章節改寫為先裝 uv，再 `marketplace add`／`plugin install`；移除「尚未驗證真實資料、OAuth」與 ChatGPT TODO，改寫為實際驗證狀態。

驗證：
- Windows 11、uv 0.13.3、Claude Code 2.1.301：在暫存專案以 local scope 從本機路徑加入 marketplace 並安裝，`claude mcp list` 顯示 `plugin:seo-pulse:seo-pulse ✔ Connected`，啟動命令為 uv；測完已移除。
- 以 MCP stdio 用戶端用同一 uv 命令呼叫 `weekly_report`（fixture）成功；隔離環境含 mcp 1.30.0 與 Google 套件。
- pytest：121 passed（原 119 + 2）。
- 真實資料：同日以 `sc-domain:lslabs.tw` 與 LS-Labs 的 GA4 資源，經 Desktop OAuth 唯讀授權，`weekly_report` JSON 正常回傳；憑證與 token 都在 repo 外。
- repo 改公開後（同日）：`claude plugin marketplace add Wenqing950519/lslabs-seo-pulse` 與 `plugin install seo-pulse@lslabs-seo-pulse`（local scope）在 Windows 11 安裝成功，快取於 `~/.claude/plugins/cache/lslabs-seo-pulse/seo-pulse/0.1.0`，`claude mcp list` ✔ Connected；以同一 uv 命令呼叫 `list_sites` 與 `weekly_report(format="markdown")` 正常。測完已解除安裝、移除 marketplace 與快取。
- 未驗證：Codex、Cursor 實際掛載。

# 2026-10-21 Skill 引用規則改寫；README 文字整理

- 兩份 Skill（`skill/SKILL.md`、`skills/seo-pulse/SKILL.md`）改寫：第 6 條「AI 引用：待 01 研究數據」改為「建議的依據只限週報表格數字與 `docs/rules.md` 規則定義，不引用外部研究、產業數據或 LS-Labs 研究結論」；補上摘要與建議的寫法順序、小樣本只寫觀察不寫動作、不替使用者決定門檻。工具未改，tool-contract 不變。
- README：移除 Codex／Cursor 與驗證狀態的說明文字，只保留安裝方式；週報流程段落改寫為新的引用規則。
- 決定：CTR 基準值 2026 年 11 月中旬累積四週真實資料後換成本站中位數；Codex、Cursor 不另行實測。

# 2026-10-21 雲端版第一階段（遠端化地基）

依規格 `projects/ls-labs-reports/handoffs/2026-10-21-seo-pulse-cloud-chatgpt-phase1.md`，分支 `feat/remote-http-phase1`（基於 master `2470d53`），本階段只做地基：同一份程式碼支援 stdio 與 streamable HTTP 兩種傳輸，工具加上 annotations，網站／GA4 資源改成可選的工具參數，認證邏輯抽成可替換的介面。**本階段完成後仍無法在 chatgpt.com 使用**（沒有公開 HTTPS 主機、沒有 OAuth），這是預期結果；詳見「未做項目」。

## 改了什麼

- **streamable HTTP 傳輸模式**（`seo_pulse_mcp/server.py`）：新增 `seo-pulse serve --transport http [--host] [--port] [--allow-unauthenticated-remote]`，`python -m seo_pulse_mcp.server --transport http` 同樣可用；環境變數 `SEO_PULSE_TRANSPORT`、`SEO_PULSE_HTTP_HOST`、`SEO_PULSE_HTTP_PORT`。CLI 參數優先於環境變數；不帶任何參數時仍是 stdio，`.mcp.json`／`.codex-mcp.json`／`seo-pulse auth` 完全不動。端點固定在 `/mcp`，`stateless_http=True`。
- **非本機綁定的安全底線**：預設只綁 `127.0.0.1`／`localhost`／`::1`；綁其他位址（例如 `0.0.0.0`）沒加 `--allow-unauthenticated-remote` 會直接拒絕啟動（非零結束、繁中錯誤），加了會在 stderr 印警告。DNS rebinding 保護沿用 SDK 對 loopback host 的預設行為（見下「設計理由」），沒有主動關閉。
- **工具 annotations**（`server.py`）：7 個工具全部加 `ToolAnnotations(title=..., readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)`；`scripts/generate_tool_contract.py` 把 `title`／`annotations` 納入 contract 與每個工具、整體指紋的 SHA-256，`contract_format` 升為 2，`diff_contracts` 也比對這兩個欄位。
- **網站與 GA4 資源改成工具參數**（`server.py`、新檔 `seo_pulse_mcp/resources.py`、`connectors/__init__.py`、`hosts.py`、`report.py`）：`gsc_query`／`gsc_compare_weeks`／`weekly_report` 加選填 `site_url`；`ga4_report`／`ga4_compare_weeks`／`weekly_report` 加選填 `property_id`；三個 GA4 工具都加選填 `production_hosts`（`list[str]` 或逗號字串）。優先順序一律「工具參數 > 環境變數」；`production_hosts` 沒給時，若有 `site_url` 會從其網域推導（見下「production_hosts 推導規則」），推導不出來才退回環境變數。格式錯誤（`property_id` 非純數字、`site_url` 非 `sc-domain:`／`http(s)://` 開頭）回傳清楚的繁中錯誤。`get_connectors()` 的 `uses_default_hosts` 擋 Google 模式沿用 `example.com` 的檢查，改成有參數時用參數判斷；`gsc_query`／`gsc_compare_weeks` 補上這段判斷邏輯（帶 `site_url` 時用 `resolve_production_hosts(None, site_url, settings)` 的結果判斷，不帶時維持 0.1.0 行為），避免 Google 模式下只傳 `site_url`、沒設 `SEO_PULSE_PRODUCTION_HOSTS` 時被誤擋；`ga4_report`／`ga4_compare_weeks` 本來就沒有 `site_url`，維持原狀。這段 `gsc_query`／`gsc_compare_weeks` 的判斷修正本身沒有改到工具 schema；但本階段整體有新增 annotations、新增選填參數並調整描述，`contract_format` 已升為 2，`tool-contract.json` 已重新產生（版本 0.2.0），`--check` 通過。沒做選做的 `list_ga4_properties`。
- **版本 0.2.0**：`pyproject.toml`、三份 `plugin.json`、`tool-contract.json` 一致（`marketplace.json` 沒有版本欄位，不用改）；`uv.lock` 重新 lock 只更新本專案版本號，沒有新增套件。
- **serverInfo.version**：`initialize` 回傳的 `serverInfo.version` 改為套件版本 0.2.0（`branding.py` 的 `PACKAGE_VERSION`，先讀 `importlib.metadata`，退回 `pyproject.toml`，再退回固定字串；在 `FastMCP` 建立後設定 `mcp._mcp_server.version`），不再回傳 mcp SDK 版本 1.30.0。`serverInfo` 不在 tool-contract 範圍內，所以 contract 不用重新產生。
- **Server instructions**：`FastMCP("seo-pulse", instructions=...)` 加入 638 字的繁中說明，前 512 字內逐字包含「先 list_sites 驗證」與「用 weekly_report(format="markdown")、只換兩段佔位、數字不改」；涵蓋 `site_url`／`property_id` 用法、`fixture: true` 要明說是假資料、不引用外部研究。`skills/seo-pulse/SKILL.md` 第一段唯讀驗證補上新參數用法，與 instructions 不矛盾；兩份 Skill 檔都保留。
- **CredentialProvider 抽象層**（新檔 `seo_pulse_mcp/connectors/credentials.py`）：把 `connectors/google.py` 原本的 `_credentials()` 邏輯、`_save_token()`、scopes、`authenticate()` 整段搬進去，行為、錯誤訊息、檔案權限（0o700、原子寫入、scope 完全相符才沿用）完全不變；`google.py` 從這個新模組 re-export，維持舊有 import 路徑可用。`GoogleGSCConnector`／`GoogleGA4Connector` 新增建構參數 `credential_provider`（預設 `LocalFileCredentialProvider`），`.get(service, context)` 的 `context` 預留每次請求的使用者身分，本階段一律 `None`。第二階段 `RemoteUserCredentialProvider` 的規劃寫在 `docs/credential-provider.md`，只有說明、沒有實作。
- **文件**：README 新增「兩種執行模式」章節（stdio 現行做法；本機 HTTP 僅供本機測試、無認證、不可對外開放的警告）與「指定網站與 GA4 資源」參數優先順序表；原本「token 存在你的電腦，不經過我們的伺服器」沒有改動，也沒有加回「可用於 ChatGPT 網頁版」的說法。
- **驗收用 client 腳本**（新檔，只是交付證據用，不是測試，沒有新依賴）：
  - `scripts/smoke_stdio_client.py`：用 `mcp.client.stdio.stdio_client` 依照 `.mcp.json` 與 `.codex-mcp.json` 原本寫的 command/args 原樣啟動兩個 stdio 伺服器（`${CLAUDE_PLUGIN_ROOT}` 換成 repo 絕對路徑、cwd 固定為 repo 根目錄、`SEO_PULSE_CONNECTOR=fixture`），分別印出 `list_tools` 的工具名稱與數量、`weekly_report(format="markdown")` 的前 15 行。
  - `scripts/smoke_http_client.py`：用 `mcp.client.streamable_http.streamablehttp_client` 連到已經在跑的 `/mcp` 端點（`--url` 可覆寫，預設 `http://127.0.0.1:8000/mcp`），印出 `initialize` 的 `serverInfo`、instructions 前 512 字元、`list_tools` 每個工具的 name／title／annotations（JSON），再呼叫 `weekly_report(site_url="sc-domain:example.com", property_id="123456789", format="markdown")` 印前 15 行、`gsc_query(..., site_url="sc-domain:example.com")` 印筆數與第一筆。
  - 兩支都用 `result.structuredContent["result"]` 取回傳值（而不是解析 `content[0].text`）：實測發現 FastMCP 對 list 回傳值會依每個元素各自產生一個 `TextContent` block，單一文字塊不等於完整結果，`structuredContent` 才是結構化、好解析的來源。
  - 已在本機實際跑過：兩個 manifest 的 stdio 都成功列出 7 個工具並印出週報前 15 行；HTTP 模式實際啟動 `seo-pulse serve --transport http --port 18766` 後，`smoke_http_client.py` 成功印出 `serverInfo`（第一輪實測時 `serverInfo.version` 是 mcp SDK 版本 1.30.0，追加修正後實測為 0.2.0）、instructions 前 512 字、7 個工具的 annotations（皆為 `readOnlyHint: true`／`destructiveHint: false`／`openWorldHint: false`，title 皆有值）、`weekly_report`／`gsc_query` 帶 `site_url`／`property_id` 皆成功回傳。

## 為什麼

李昇 10/21 決定「SEO Pulse 做雲端版，讓別人也能在 ChatGPT 網頁版用」。ChatGPT 網頁版只能連遠端 streamable HTTP 伺服器，現有的 stdio-only 架構進不去；這一階段先把「同一份程式碼、兩種傳輸」的地基做好（HTTP 入口、annotations、多網站／資源參數、認證抽象層），讓第二階段只要補上公開 HTTPS 主機與 OAuth proxy，就能接上 ChatGPT 的「Add custom MCP server」。本階段刻意不做任何需要花錢、對外公開或動到他人帳號的事。

## 設計理由

- **`stateless_http=True`**：7 個工具全部唯讀、每次呼叫都是獨立查詢，不需要跨請求記住任何狀態；選 stateless 讓第二階段要做水平擴充（多個伺服器行程分攤請求）時不用改這裡的設計，也省去管理 session 生命週期的複雜度。
- **`openWorldHint=False`**：7 個工具只呼叫 Google 兩個唯讀 API（GSC、GA4 report），不會呼叫使用者指定以外、不可預期的外部服務，也不會對外寫入；`openWorldHint=True` 是給「可能呼叫任意外部系統」（例如通用網頁搜尋）的工具用的，不符合這裡的情況。
- **production_hosts 推導規則**：`sc-domain:x` 或 `http(s)://x/` 推導出 `x` 時，同時納入 `x` 與 `www.x` 兩者（例如 `example.com` 與 `www.example.com`），因為同一個網域屬性常同時涵蓋裸網域與 www 子網域，只納入其中一個會讓另一邊的 GA4 流量被誤判為污染而排除；推導邏輯只在工具明確傳入 `site_url` 時觸發，只設環境變數時不受影響，確保 A5（只設環境變數的回歸相容）成立。
- **DNS rebinding 保護**：官方 SDK 只在 `FastMCP(host=...)` 建構時看到 `127.0.0.1`／`localhost`／`::1` 才會自動套用保護設定，其他 host 預設不啟用（為了相容舊版行為）。因為伺服器物件在模組載入時就建立好（供 `@mcp.tool()` 註冊使用），實際的 host 要等 CLI／環境變數解析完才知道，所以 `serve()` 裡用跟 SDK 建構式完全一樣的邏輯重算一次 `transport_security`：loopback 就套用保護、非 loopback 就維持 SDK 本來的預設（不啟用），沒有在任何情況下主動關閉保護。

## 未做項目（第二階段，待李昇決定後另開規格）

- Google Web OAuth client、依使用者加密保存 refresh token、資料庫或 KV。
- ChatGPT 用的 OAuth 2.1（protected resource metadata、AS metadata、PKCE、CIMD／DCR、`offline_access`、每次請求驗證 token）與對應的 OAuth proxy。
- `RemoteUserCredentialProvider` 的實作（目前只有 `docs/credential-provider.md` 的規劃說明）。
- 選做的 `list_ga4_properties` 工具。
- Dockerfile、任何部署設定、公開 HTTPS 主機、Secure MCP Tunnel。
- 隱私權政策、服務條款、OpenAI 目錄上架。
- `allowed_hosts`／DNS rebinding 設定：綁非本機位址時 SDK 預設不啟用保護，對外部署前要設定 `TransportSecuritySettings` 的 `allowed_hosts`／`allowed_origins`。
- fixture 模式會忽略 `site_url`／`property_id` 參數（一律回傳同一份假資料），本階段不修，第二階段再處理。

## 新依賴

零。`uv.lock` 的異動只有本專案版本號 `0.1.0` → `0.2.0`（與一行解析標記順序的無害變動），沒有新增或升級任何套件；streamable HTTP 用到的 `starlette`／`uvicorn` 等已隨官方 `mcp` SDK 的既有依賴安裝，不是本次新增。

## 驗證結果

- `uv run --extra test --extra google pytest`：152 passed（原本 121 + 31 個新測試），0 failed、0 skipped。
- `uv run --extra test --extra google python scripts/generate_tool_contract.py --check`：`OK: 本機伺服器與 tool-contract.json 一致`。
- 版本一致性：`pyproject.toml`、三份 `plugin.json`、`tool-contract.json` 皆為 `0.2.0`。
- `uv run --extra google python scripts/smoke_stdio_client.py`：`.mcp.json`、`.codex-mcp.json` 兩個 manifest 都成功列出 7 個工具，fixture 模式 `weekly_report(format="markdown")` 正常回傳。
- 實際啟動 `uv run --extra google python -m seo_pulse_mcp.server --transport http --port 18766` 後執行 `scripts/smoke_http_client.py --url http://127.0.0.1:18766/mcp`：`serverInfo` 正常（第一輪實測時 `serverInfo.version` 是 mcp SDK 版本 1.30.0，追加修正後實測為 0.2.0）、instructions 前 512 字含規格要求的兩句、7 個工具的 `title`／`annotations` 都正確（`readOnlyHint: true`、`destructiveHint: false`、`openWorldHint: false`）、`weekly_report`／`gsc_query` 帶 `site_url`／`property_id` 都成功回傳。
- 兩種啟動方式實測：`seo-pulse serve --transport http --port 18801` 與 `SEO_PULSE_TRANSPORT=http SEO_PULSE_HTTP_PORT=18802 python -m seo_pulse_mcp.server` 都只監聽 `127.0.0.1`（`ss -ltn` 確認），`scripts/smoke_http_client.py` 對兩者都回傳 0。
- DNS rebinding 保護實測：帶 `Host: evil.example` 的請求回 HTTP 421（`Invalid Host header`）。
- 安全底線實測：`--host 0.0.0.0` 不加旗標時拒絕啟動（exit 1、繁中錯誤）；加 `--allow-unauthenticated-remote` 時 stderr 印警告後正常啟動。
- `claude plugin validate --strict .` 通過。本階段沒有用 `claude plugin install` 實際掛載（避免動到本機 Claude Code 設定），A1 以 `tests/test_plugin_launch.py` 與 `scripts/smoke_stdio_client.py` 驗證。
- 追加修正（10/21 08:08 後）重跑：`claude plugin validate --strict .` ✔ Validation passed；`generate_tool_contract.py --check` OK；`smoke_stdio_client.py` 兩個 manifest 都列出 7 個工具、exit 0。
- 實測只設 `SEO_PULSE_ALLOW_UNAUTHENTICATED_REMOTE=1`、`--host 0.0.0.0`、不加旗標：拒絕啟動（exit 1），確認環境變數無法解除限制。
- HTTP 實測 `initialize` 的 `serverInfo` 為 `{name: seo-pulse, version: 0.2.0}`；新測試 `tests/test_server.py::test_initialize_reports_package_version_as_server_info`、`tests/test_http_transport.py::test_env_var_alone_does_not_allow_remote` 通過。
# 2026-10-21 PR #2 review fixes

## 改了什麼

- 修正跨網站週報：每次呼叫建立獨立設定，GA4 清理與異常偵測使用相同正式網域，避免 A10／A11 等規則漏報；保留原始資料污染比例。
- `site_url` 同步決定週報網站與 A9 canonical 判定。URL-prefix 保留 scheme／host／port；網域屬性保留其範圍內既有 canonical，跨網域時預設 HTTPS。後續未帶參數的呼叫仍使用原環境設定。
- 統一工具註冊時的 docstring 縮排，修正 Python 3.12 與 3.13+ 編譯差異造成的合約指紋不一致；既有 0.2.0 工具合約內容不變。

## 驗證結果

- 鎖定依賴、Python 3.12；pytest 161 passed（新增 9 案例）；tool-contract `--check` 通過；兩份 plugin manifest 的 stdio smoke 與 HTTP fixture smoke 通過。不使用真實 Google 資料。

# 2026-10-21 0.3.0 雲端版：ChatGPT 插件試點（審計 docs/audits/2026-10-21-seo-pulse-pr2-cloud-audit.md 的修正）

## 改了什麼

- **參數路徑缺陷（審計 §3.B）**
  - 網域屬性的其他子網域改為另列 `subdomain_sessions`／`subdomain_hosts`，不再算入污染。新增 `pollution_ratio`；`pollution_warning` 只看非同網域主機。`excluded_sessions`／`excluded_ratio` 意義不變。
  - URL-prefix 屬性只推導該主機：`https://blog.example.com/` 不再推出 `www.blog.example.com`。
  - 空的 `sc-domain:`、沒有主機的網址、含空白或 scheme 的網域一律拒絕，不再靜默退回環境變數。
  - `SEO_PULSE_HTTP_PORT` 非整數時回繁中錯誤；另讀 Cloud Run 的 `PORT`。
  - fixture 模式收到 `site_url`／`property_id` 時，週報維持 example.com，並在 warnings 註明參數已忽略。
- **結構問題（審計 §3.A）**
  - 工具改在背景執行緒執行（`runtime.py`），並以 `CapacityLimiter` 限制同時執行數。同步的 Google 呼叫不再卡住事件迴圈；限制器依事件迴圈分開建立。
  - 新增 `Caller`（`caller.py`）傳遞每個請求的使用者。`get_connectors()` 看到 `Caller` 就改用 `RemoteUserCredentialProvider`；雲端版不讀網站與資源的環境變數，缺參數時回錯誤，提示先 `list_sites`／`list_ga4_properties`。
  - SEO Pulse 自己當 OAuth 授權端（`auth.py`），Google 負責登入。DCR、PKCE S256、`resource` 綁定與 `validate_token_resource` 都已實作，不需要 OAuth proxy 或外部授權服務。
    - 無狀態：client_id 以 HMAC 簽章，授權碼與存取／更新憑證以 Fernet 加密並攜帶 Google refresh token，不需要資料庫。
    - DCR 只接受 ChatGPT、Claude 與本機 loopback 的 redirect。
    - 有邀請名單，每次請求都重新檢查。
  - 刷新競態：雲端每位使用者一把鎖，並快取短期權杖；本機 provider 改為程序共用，並在記憶體快取有效憑證。
- **上架與 Google 要求（審計 §4）**
  - `hosting.py` 提供 `/.well-known/oauth-protected-resource`（根目錄與 `/mcp` 兩處）與 AS metadata；AS metadata 補上 `none` 認證方式。另有 `/healthz`、`/` 轉產品頁、網域驗證檔。
  - uvicorn 不送 `server` 標頭；雲端模式關閉 access log，因為查詢字串含 OAuth code。
  - `Dockerfile`；`docs/hosting.md`（環境變數、GCP 設定、Cloud Run 部署、費用上限、上架對照）。
  - `distribution/openai/`（plugin.json、遠端 mcp.json 使用 OAuth DCR）與 `scripts/build_openai_plugin.py`。
- **成本**：每人每分鐘、每人每日、全站每日的呼叫上限，以及相同呼叫的結果快取，預設值對應 Cloud Run 免費額度。`--max-instances 1` 為硬上限。
- **導流**
  - 週報頁尾連到 `https://lslabs.tw/seo-pulse/`，UTM 區分本機與雲端。
  - `serverInfo` 帶 `websiteUrl` 與 `icons`。
  - instructions 加一句「說明週報由 LS-Labs SEO Pulse 產生」；伺服器根目錄轉到產品頁。
- 新工具 `list_ga4_properties`（Analytics Admin API）；GA4 工具新增選填 `site_url`。
- 版本 0.3.0，tool-contract 重新產生；`seo-pulse keygen` 產生金鑰。
- 文件：README 改為三種執行模式，Skill 加入雲端流程；`docs/credential-provider.md` 由規劃改寫為實作說明。

## 為什麼

使用者 10/21 決定 SEO Pulse 以插件形式進入 ChatGPT 等網頁版 AI，模型與方案成本由使用者端負擔，作為插件市場的試點，並在合規範圍內導流到 LS-Labs。決策見 home `docs/DECISION_LOG.md` LSL-D-008。

## 設計理由

- **無狀態憑證**：不用資料庫，因此沒有主機以外的費用，也沒有集中保存的 Google 授權可以外洩。
  - 代價一：已發出的更新憑證無法單獨作廢，改用 Google 端撤銷與邀請名單即時檢查來處理。
  - 代價二：授權碼單次使用只在單一程序內成立，`--max-instances 1` 讓它精確。
- **子網域另列而不納入**：網域屬性的 GSC 數字包含子網域，但哪些子網域算正式站是使用者的範圍選擇，不由程式代為決定。lslabs.tw 自己只算主站，維持既有決定。

## 未做項目

- 實際部署、`pulse.lslabs.tw` 網域、Google 品牌驗證、OpenAI 開發者驗證與上架審核材料（影片、測試案例、審核帳號），都需要人工操作與授權。
- CIMD（Client ID Metadata Document）：SDK 1.30 伺服器端未支援，目前用 DCR，ChatGPT 支援 DCR。

## 驗證結果

見本次結案紀錄；pytest、contract `--check`、stdio smoke、本機 HTTP smoke 與雲端模式本機冒煙測試。
