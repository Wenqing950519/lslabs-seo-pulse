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
- 未驗證：Codex、Cursor 實際掛載；從 GitHub marketplace 安裝（repo 改公開後再測）。
