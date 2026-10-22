# 雲端模式：部署、設定與成本上限

上線後的狀態檢查、用量、費用與警示門檻見 [monitoring.md](monitoring.md)。

雲端模式讓 ChatGPT 等網頁版 AI App 以插件方式使用 SEO Pulse。工具、週報與規則和本機版完全相同，差在三件事：

- 每個使用者用自己的 Google 帳號登入；
- 伺服器不設預設網站；
- 通過認證的工具呼叫共用 Firestore 次數限制；併發限制仍以程序為單位，工具次數不是雲端帳單的硬上限。

設定 `SEO_PULSE_PUBLIC_URL` 就會啟用雲端模式。沒有設定時，`--transport http` 仍是只限本機、沒有認證的測試模式。

## 架構

```
ChatGPT ──OAuth 2.1 + PKCE──▶ SEO Pulse（授權端 + MCP 伺服器）──Google 登入──▶ Google
   │                                   │
   └── Bearer token（加密，內含 Google 授權）──▶ /mcp ──唯讀 API──▶ Search Console / GA4
```

- **SEO Pulse 自己就是授權端**，Google 只負責登入。ChatGPT 需要的 metadata、DCR 註冊、PKCE S256、`resource` 綁定、撤銷都由 `seo_pulse_mcp/auth.py` 提供，不另外付費使用 Auth0、Stytch 這類授權服務。
- **Firestore 只保存限制與防重放所需的紀錄，不保存 Google 授權或報表。**
  - 註冊資料以 HMAC 簽進 client_id。
  - 授權碼、存取憑證、更新憑證都是 Fernet 加密的字串，內含使用者的 Google refresh token。這些字串由 AI App 保管，伺服器每次請求時在記憶體解密。
  - 記憶體裡保存 Google 短期存取權杖（最長 1 小時）及相同參數的工具結果（預設 15 分鐘）；重啟就清空。
  - Firestore 的 `seo_pulse_state` collection 保存一筆全站計數、每位使用者一筆計數與最近 60 秒的呼叫時間，以及已兌換授權碼的 HMAC-SHA256 摘要。使用者識別也經獨立祕密金鑰 HMAC；不存原始 `sub`、email、授權碼、Google token、工具參數或報表。
  - 計數文件每天覆寫，`expire_at` 設為該 UTC 日結束後 24 小時；授權碼文件設為授權碼到期後 60 秒。Firestore TTL 通常在到期後 24 小時內刪除，不保證準時；到期與使用次數由程式檢查，授權判斷不依賴 TTL 清除速度。
- **效期**：授權碼 120 秒且只能用一次，以 Firestore 原子交易跨程序、重啟與 revision 共同保證；存取憑證 1 小時；更新憑證 30 天，每次使用都會換新。
- **撤銷**：
  - 使用者到 Google 帳戶的第三方連線頁移除 SEO Pulse，Google 授權依撤銷傳播時間失效。SEO Pulse 的加密憑證不會因此立即作廢；既有記憶體結果快取最長 15 分鐘，短期 Google 存取憑證最長 1 小時，不能保證所有連線立即失效。緊急停權須同步從試點邀請名單移除帳號並套用設定。
  - 從邀請名單移除某個 email，下一個請求就會被拒。
  - 尚未建立更新憑證的撤銷清單，不能單獨作廢某一張已發出的更新憑證；Firestore 的授權碼防重放不等同於 refresh token 撤銷。
- **轉址白名單**：DCR 只接受 `chatgpt.com`、`chat.openai.com`、`claude.ai`、`claude.com` 與本機 loopback。這可以防止第三方註冊自己的 redirect，騙使用者授權後拿走憑證。

## 環境變數

| 變數 | 必填 | 說明 |
|---|---|---|
| `SEO_PULSE_PUBLIC_URL` | ✔ | 對外網址，例如 `https://pulse.lslabs.tw`（https、不含路徑）。MCP 端點是它加上 `/mcp` |
| `SEO_PULSE_GOOGLE_WEB_CLIENT_ID`／`_SECRET` | ✔ | Google OAuth「網頁應用程式」client；secret 放 Secret Manager |
| `SEO_PULSE_TOKEN_KEYS` | ✔ | Fernet 金鑰，用逗號分隔。第一把用來加密，所有金鑰都能解密，所以輪替時把新金鑰放最前面即可。用 `seo-pulse keygen` 產生，放 Secret Manager |
| `SEO_PULSE_FIRESTORE_PROJECT` | ✔ | 共享限制資料庫所在專案，正式站為 `ga4-mcp-506714` |
| `SEO_PULSE_FIRESTORE_DATABASE` | | Firestore Native 資料庫，預設 `(default)` |
| `SEO_PULSE_STATE_NAMESPACE` | | 預設 `seo-pulse`；同一服務的所有 revision 必須使用相同值，不能拿它做版本號 |
| `SEO_PULSE_STATE_HMAC_KEY` | ✔ | 至少 32 bytes 的獨立隨機祕密，放 `seo-pulse-state-hmac`。所有 revision 必須相同，不能隨 token 加密金鑰輪替；更換會切換紀錄 ID，需另做遷移或停用舊憑證 |
| `SEO_PULSE_ALLOWED_EMAILS`／`SEO_PULSE_ALLOWED_EMAIL_DOMAINS` | 二選一 | 試點邀請名單。兩者都沒設時，必須明確設定 `SEO_PULSE_OPEN_SIGNUP=1` 才會開放所有帳號，否則拒絕啟動 |
| `SEO_PULSE_RATE_PER_MINUTE` | | 每位使用者每分鐘次數，預設 20 |
| `SEO_PULSE_RATE_PER_DAY` | | 每位使用者每日次數，預設 200 |
| `SEO_PULSE_DAILY_TOTAL` | | 共享 namespace 每日總次數，預設 2000；UTC 日界線重置 |
| `SEO_PULSE_CACHE_SECONDS` | | 相同呼叫的結果快取秒數，預設 900。命中快取不計次數，也不呼叫 Google |
| `SEO_PULSE_MAX_CONCURRENCY` | | 每個程序同時執行的工具數，預設 8；不是跨實例總併發 |
| `SEO_PULSE_VERIFICATION_FILES` | | 網域驗證檔，格式 `/路徑=內容`，例如 OpenAI 上架要求的純文字 challenge |
| `SEO_PULSE_ALLOWED_REDIRECT_HOSTS`／`SEO_PULSE_ALLOWED_HOSTS`／`SEO_PULSE_ALLOWED_ORIGINS` | | 覆寫 DCR 轉址主機，或增加允許的 Host、Origin |

雲端模式的每分鐘、每日、全站總次數與併發數必須是正整數；填 `0` 或負數會拒絕啟動，避免誤關成本限制。快取秒數可設 `0` 關閉快取，不接受負數。本機模式維持既有不限次數的設定，也不載入 Firestore client。

缺少共享儲存設定會拒絕啟動；Firestore 交易不可用時拒絕新的工具執行與授權碼兌換，不退回記憶體計數。快取命中雖不扣額度，仍要唯讀確認儲存服務可用。每次等待共享儲存最多 8 秒，讀取 RPC 為 3 秒、交易最多嘗試 3 次；同步 SDK 的交易可能在逾時後完成扣額或授權碼登記，但不會因此繼續呼叫 Google。每程序最多 8 個共享儲存操作在執行，避免逾時背景工作無限累積。工具開始前扣額，Google 失敗也不退款，以免錯誤重試繞過限制。

不要在雲端設定 `SEO_PULSE_GSC_SITE_URL`、`SEO_PULSE_GA4_PROPERTY_ID`、`SEO_PULSE_PRODUCTION_HOSTS`。雲端版必須由使用者指定網站：先呼叫 `list_sites`、`list_ga4_properties`，再帶入 `site_url`、`property_id`。

## Google Cloud 設定

三個專案分工（2026-10-21 起）：

- **lslabs-seo-pulse**（不需帳單）：專門給雲端版的 OAuth 同意畫面（品牌「SEO Pulse」）與網頁應用程式 OAuth client，Search Console／GA4 Data／Analytics Admin API 在這裡啟用，API 配額算在這個專案。
- **ga4-mcp-506714**：Cloud Run 主機、Cloud Build、Artifact Registry、Firestore Native、Secret Manager（`seo-pulse-token-keys`、`seo-pulse-google-secret`、`seo-pulse-state-hmac`）與預算通知。
- **geocheck-508206**：本機版自備的 OAuth 電腦版 client（不變）。

這樣分的原因有兩個：
- geocheck-508206 與 ga4-mcp-506714 的同意畫面已分別屬於 GeoCheck 與純家教，一個專案只能有一套品牌。
- 帳單帳戶已連結 5 個專案，達到 Google 上限，主機只能放在已有帳單的專案。

1. **啟用 API**：Google Search Console API、Google Analytics Data API、Google Analytics Admin API。Admin API 給 `list_ga4_properties` 使用。
2. **OAuth 同意畫面**：
   - 應用程式名稱：SEO Pulse；
   - 首頁：`https://lslabs.tw/seo-pulse/`；
   - 隱私權政策：`https://lslabs.tw/seo-pulse/privacy/`；
   - 服務條款：`https://lslabs.tw/seo-pulse/terms/`；
   - 授權網域：`lslabs.tw`；
   - 範圍：`openid`、`email`、`webmasters.readonly`、`analytics.readonly`。
3. **品牌驗證**：申請後同意畫面才會顯示名稱與圖示。`lslabs.tw` 已在 Search Console 驗證，首頁與隱私權政策都在同一個網域。
   - 依 2026-10-21 驗證中心的結果，兩個唯讀範圍不需要送範圍審查。上架前請再核對一次。
   - 範圍若被改列為 sensitive，未驗證期間 Google 會顯示「未驗證」警告，並把新使用者限制在 100 人。試點邀請名單應維持在這個數字以內。
4. **建立網頁應用程式 OAuth client**：已授權的重新導向 URI 填 `https://pulse.lslabs.tw/oauth/google/callback`。
5. **發布狀態維持「正式版」**。測試版的 refresh token 7 天就會失效。

## 部署（Cloud Run，asia-east1，專案 ga4-mcp-506714）

在 repo 根目錄執行，或交給 Cloud Build：

先啟用 Firestore API，建立 `asia-east1` 的 Native `(default)` 資料庫。正式執行身分使用 `seo-pulse-runtime@ga4-mcp-506714.iam.gserviceaccount.com`，授予 `roles/datastore.user` 與上述三個 secret 的個別讀取權。對 `seo_pulse_state` collection group 的 `expire_at` 啟用 TTL：

```bash
gcloud firestore fields ttls update expire_at --collection-group=seo_pulse_state --enable-ttl --database='(default)' --project=ga4-mcp-506714
```

Dockerfile 以 `uv sync --frozen --extra google --extra hosted` 安裝 Google 與 Firestore client。本機 stdio 不需 `hosted` extra。

```bash
gcloud run deploy seo-pulse --source . --region asia-east1 --project ga4-mcp-506714 --service-account seo-pulse-runtime@ga4-mcp-506714.iam.gserviceaccount.com --min-instances 0 --max-instances 1 --concurrency 20 --cpu 1 --memory 512Mi --timeout 120 --cpu-throttling --set-env-vars SEO_PULSE_PUBLIC_URL=https://pulse.lslabs.tw,SEO_PULSE_GOOGLE_WEB_CLIENT_ID=<client id>,SEO_PULSE_ALLOWED_EMAILS=<邀請名單>,SEO_PULSE_FIRESTORE_PROJECT=ga4-mcp-506714,SEO_PULSE_STATE_NAMESPACE=seo-pulse --set-secrets SEO_PULSE_GOOGLE_WEB_CLIENT_SECRET=seo-pulse-google-secret:latest,SEO_PULSE_TOKEN_KEYS=seo-pulse-token-keys:latest,SEO_PULSE_STATE_HMAC_KEY=seo-pulse-state-hmac:latest --allow-unauthenticated
```

- `--allow-unauthenticated` 指的是 Cloud Run 不做 IAM 檢查。認證由 SEO Pulse 自己的 OAuth 負責，ChatGPT 才連得到。
- `--max-instances 1` 限制正常擴容。新舊 revision 共用同一 Firestore 專案、資料庫、namespace、HMAC key 時，呼叫次數與授權碼防重放持續生效；首次由記憶體版升級時，要將流量全數切到新版，停用仍可接受請求的舊 revision。併發限制仍以程序為單位。Cloud Run 可能暫時超出最大實例數，見 [官方說明](https://docs.cloud.google.com/run/docs/configuring/max-instances)。
- **自訂網域 `pulse.lslabs.tw`**：
  - 優先用 Cloud Run 網域對應（免費）。上線前先確認 asia-east1 支援；不支援就改用 Firebase Hosting 轉到 Cloud Run（免費額度內）。
  - 不要用外部負載平衡器，月費約 US$18 起。
- **上線後檢查**：
  - `GET /health` 經唯讀 Firestore 交易後回 `ok`，不可用或逾時回 503；不扣額度也不呼叫 Google API；
  - `GET /` 轉到產品頁；
  - `GET /.well-known/oauth-protected-resource` 與 `/.well-known/oauth-authorization-server` 都回 JSON；
  - `POST /mcp` 沒帶 token 時回 401，並附 `WWW-Authenticate`。

## 費用：誰付什麼、上限在哪

| 項目 | 付費方 | 實際支出 |
|---|---|---|
| 模型 token、ChatGPT 方案 | 使用者 | 0（LS-Labs） |
| Search Console API | — | 免費，只有配額（官方 pricing 頁明載） |
| GA4 Data API | — | 官方未公告收費，只有配額。每日 token 配額算在**使用者自己的 GA4 資源**上 |
| Analytics Admin API | — | 只有配額 |
| 授權端 | — | 內建於伺服器，沒有另付授權服務費 |
| Firestore | LS-Labs | 交易讀寫與儲存依用量計費；TTL 刪除不適用免費用量，不能保證 NT$0 |
| Cloud Run | LS-Labs | 免費額度內為 0（見下） |
| Secret Manager、Artifact Registry、Cloud Logging | LS-Labs | 3 個 secret、映像檔與日誌依實際用量、版本保留及免費額度核對 |

### Cloud Run 免費額度與程式上限的對應

以請求計費（`--cpu-throttling`，只在處理請求時計 CPU）的每月免費額度是 **180,000 vCPU 秒、360,000 GiB 秒、200 萬次請求**（Google Cloud Run 價格頁）。

- **預設上限**：每日總計 2,000 次。假設每次最多 3 秒 CPU，一天是 6,000 vCPU 秒，30 天是 180,000 vCPU 秒，剛好等於免費額度。
- **記憶體**：0.5 GiB × 3 秒 × 2,000 次 × 30 天 = 90,000 GiB 秒，遠低於 360,000。
- **快取**：重複查詢命中快取時不呼叫 Google、不計工具次數，但處理 HTTP 與回傳仍消耗 CPU。

每次未命中快取的工具預留額度約需 2 次 Firestore 讀取與 2 次寫入；快取命中與 `/health` 各需讀取，共享交易重試增加用量。單次工具可能呼叫多個 Google API；工具次數限制不是 Google 請求數或帳單金額的硬上限。交易與保留設計依 [Firestore 原子交易](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions) 與 [TTL 官方說明](https://docs.cloud.google.com/firestore/native/docs/ttl)。

### 最壞情況

大量未認證請求也可能消耗 Cloud Run 資源，且不計入工具次數。先前約 US$60／月的估算只涵蓋單一 1 vCPU 實例滿載的 CPU，未涵蓋記憶體、請求、網路、其他服務與暫時超額實例，不能當成帳單上限。費用須以當時價目、帳單與預算警示核對；警示本身不會自動停機。

### 費用約束清單（上線前完成）

1. 在 GCP 帳單建立預算 **US$5／月**，並設定 50%、90%、100% 的 email 通知。已建立：帳單帳戶幣別是新台幣，所以設為 NT$150／月，範圍限 ga4-mcp-506714。
2. Cloud Run 設定 `--max-instances 1`、`--min-instances 0`、`--cpu-throttling`。
3. 應用程式上限維持預設，或調得更低：`SEO_PULSE_DAILY_TOTAL`、`SEO_PULSE_RATE_PER_DAY`。
4. 邀請名單控制人數。依每人每日 200 次計算，2,000 次的總上限大約可以支撐 10 位重度使用者同時用滿。
5. 要停止對外服務時移除 `allUsers` 的 `roles/run.invoker`，完整命令見 monitoring.md 第 10 節；不要以 `--max-instances 0` 當作停機開關。

## 上架 ChatGPT／Codex 插件目錄的對照

| 要求（OpenAI 文件） | 狀態 |
|---|---|
| 公開 HTTPS MCP 端點、DCR、PKCE S256、protected resource metadata、`resource` 綁定 | 已部署：`https://pulse.lslabs.tw/mcp`（Cloud Run，2026-10-21） |
| 工具 annotations（readOnly／非破壞／closed-world） | 已完成，納入 tool-contract |
| website／support／privacy／terms 四個 HTTPS 網址 | 主站 `/seo-pulse/`、`#support`、`/privacy/`、`/terms/`；2026-10-21 已上線 |
| 網域驗證純文字檔 | 用 `SEO_PULSE_VERIFICATION_FILES` 提供 |
| 插件 ZIP（manifest、mcp.json、Skill、圖示，不含 secret） | `scripts/build_openai_plugin.py` |
| 開發者身分驗證、5 個正向與 3 個負向測試案例、影片、免 MFA 的審核帳號 | 需要人工準備：審核帳號是一個已連結示範 GSC／GA4 資源的 Google 帳號，並加入邀請名單 |
| 不得投放廣告或推升級；可以連到資訊頁 | 週報頁尾與 `/` 只連產品資訊頁（帶 UTM），不連到任何購買流程 |
