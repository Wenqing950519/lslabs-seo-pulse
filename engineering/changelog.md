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
