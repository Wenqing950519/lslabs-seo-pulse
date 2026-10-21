# 雲端模式：部署、設定與成本上限

上線後的狀態檢查、用量、費用與警示門檻見 [monitoring.md](monitoring.md)。

雲端模式讓 ChatGPT 等網頁版 AI App 以插件方式使用 SEO Pulse。工具、週報與規則和本機版完全相同，差在三件事：

- 每個使用者用自己的 Google 帳號登入；
- 伺服器不設預設網站；
- 所有呼叫都受成本上限約束。

設定 `SEO_PULSE_PUBLIC_URL` 就會啟用雲端模式。沒有設定時，`--transport http` 仍是只限本機、沒有認證的測試模式。

## 架構

```
ChatGPT ──OAuth 2.1 + PKCE──▶ SEO Pulse（授權端 + MCP 伺服器）──Google 登入──▶ Google
   │                                   │
   └── Bearer token（加密，內含 Google 授權）──▶ /mcp ──唯讀 API──▶ Search Console / GA4
```

- **SEO Pulse 自己就是授權端**，Google 只負責登入。ChatGPT 需要的 metadata、DCR 註冊、PKCE S256、`resource` 綁定、撤銷都由 `seo_pulse_mcp/auth.py` 提供，不另外付費使用 Auth0、Stytch 這類授權服務。
- **伺服器不保存任何使用者資料，所以不需要資料庫。**
  - 註冊資料以 HMAC 簽進 client_id。
  - 授權碼、存取憑證、更新憑證都是 Fernet 加密的字串，內含使用者的 Google refresh token。這些字串由 AI App 保管，伺服器每次請求時在記憶體解密。
  - 記憶體裡只放兩樣東西：Google 短期存取權杖（最長 1 小時）、相同參數的工具結果（預設 15 分鐘）。重啟就清空。
- **效期**：授權碼 120 秒且只能用一次（以單一程序為準）；存取憑證 1 小時；更新憑證 30 天，每次使用都會換新。
- **撤銷**：
  - 使用者到 Google 帳戶的第三方連線頁移除 SEO Pulse，所有憑證立刻失效。
  - 從邀請名單移除某個 email，下一個請求就會被拒。
  - 無狀態設計無法單獨作廢某一張已發出的更新憑證，這是不用資料庫的代價。
- **轉址白名單**：DCR 只接受 `chatgpt.com`、`chat.openai.com`、`claude.ai`、`claude.com` 與本機 loopback。這可以防止第三方註冊自己的 redirect，騙使用者授權後拿走憑證。

## 環境變數

| 變數 | 必填 | 說明 |
|---|---|---|
| `SEO_PULSE_PUBLIC_URL` | ✔ | 對外網址，例如 `https://pulse.lslabs.tw`（https、不含路徑）。MCP 端點是它加上 `/mcp` |
| `SEO_PULSE_GOOGLE_WEB_CLIENT_ID`／`_SECRET` | ✔ | Google OAuth「網頁應用程式」client；secret 放 Secret Manager |
| `SEO_PULSE_TOKEN_KEYS` | ✔ | Fernet 金鑰，用逗號分隔。第一把用來加密，所有金鑰都能解密，所以輪替時把新金鑰放最前面即可。用 `seo-pulse keygen` 產生，放 Secret Manager |
| `SEO_PULSE_ALLOWED_EMAILS`／`SEO_PULSE_ALLOWED_EMAIL_DOMAINS` | 二選一 | 試點邀請名單。兩者都沒設時，必須明確設定 `SEO_PULSE_OPEN_SIGNUP=1` 才會開放所有帳號，否則拒絕啟動 |
| `SEO_PULSE_RATE_PER_MINUTE` | | 每位使用者每分鐘次數，預設 20 |
| `SEO_PULSE_RATE_PER_DAY` | | 每位使用者每日次數，預設 200 |
| `SEO_PULSE_DAILY_TOTAL` | | 整台伺服器每日總次數，預設 2000。這是主要的成本閘門 |
| `SEO_PULSE_CACHE_SECONDS` | | 相同呼叫的結果快取秒數，預設 900。命中快取不計次數，也不呼叫 Google |
| `SEO_PULSE_MAX_CONCURRENCY` | | 同時執行的工具數，預設 8 |
| `SEO_PULSE_VERIFICATION_FILES` | | 網域驗證檔，格式 `/路徑=內容`，例如 OpenAI 上架要求的純文字 challenge |
| `SEO_PULSE_ALLOWED_REDIRECT_HOSTS`／`SEO_PULSE_ALLOWED_HOSTS`／`SEO_PULSE_ALLOWED_ORIGINS` | | 覆寫 DCR 轉址主機，或增加允許的 Host、Origin |

不要在雲端設定 `SEO_PULSE_GSC_SITE_URL`、`SEO_PULSE_GA4_PROPERTY_ID`、`SEO_PULSE_PRODUCTION_HOSTS`。雲端版必須由使用者指定網站：先呼叫 `list_sites`、`list_ga4_properties`，再帶入 `site_url`、`property_id`。

## Google Cloud 設定

三個專案分工（2026-10-21 起）：

- **lslabs-seo-pulse**（不需帳單）：專門給雲端版的 OAuth 同意畫面（品牌「SEO Pulse」）與網頁應用程式 OAuth client，Search Console／GA4 Data／Analytics Admin API 在這裡啟用，API 配額算在這個專案。
- **ga4-mcp-506714**：Cloud Run 主機、Cloud Build、Artifact Registry、Secret Manager（`seo-pulse-token-keys`、`seo-pulse-google-secret`）與預算通知。
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

```bash
gcloud run deploy seo-pulse --source . --region asia-east1 --project ga4-mcp-506714 --min-instances 0 --max-instances 1 --concurrency 20 --cpu 1 --memory 512Mi --timeout 120 --cpu-throttling --set-env-vars SEO_PULSE_PUBLIC_URL=https://pulse.lslabs.tw,SEO_PULSE_GOOGLE_WEB_CLIENT_ID=<client id>,SEO_PULSE_ALLOWED_EMAILS=<邀請名單> --set-secrets SEO_PULSE_GOOGLE_WEB_CLIENT_SECRET=seo-pulse-google-secret:latest,SEO_PULSE_TOKEN_KEYS=seo-pulse-token-keys:latest --allow-unauthenticated
```

- `--allow-unauthenticated` 指的是 Cloud Run 不做 IAM 檢查。認證由 SEO Pulse 自己的 OAuth 負責，ChatGPT 才連得到。
- `--max-instances 1` 讓程序內的計數與單次授權碼檢查都精確，同時也是費用的硬上限。
- **自訂網域 `pulse.lslabs.tw`**：
  - 優先用 Cloud Run 網域對應（免費）。上線前先確認 asia-east1 支援；不支援就改用 Firebase Hosting 轉到 Cloud Run（免費額度內）。
  - 不要用外部負載平衡器，月費約 US$18 起。
- **上線後檢查**：
  - `GET /health` 回 `ok`；
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
| 授權端、資料庫 | — | 0（內建於伺服器、無狀態） |
| Cloud Run | LS-Labs | 免費額度內為 0（見下） |
| Secret Manager、Artifact Registry、Cloud Logging | LS-Labs | 2 個 secret、單一映像檔、少量日誌，都在免費額度內 |

### Cloud Run 免費額度與程式上限的對應

以請求計費（`--cpu-throttling`，只在處理請求時計 CPU）的每月免費額度是 **180,000 vCPU 秒、360,000 GiB 秒、200 萬次請求**（Google Cloud Run 價格頁）。

- **預設上限**：每日總計 2,000 次。假設每次最多 3 秒 CPU，一天是 6,000 vCPU 秒，30 天是 180,000 vCPU 秒，剛好等於免費額度。
- **記憶體**：0.5 GiB × 3 秒 × 2,000 次 × 30 天 = 90,000 GiB 秒，遠低於 360,000。
- **快取**：重複查詢命中快取時不耗 CPU 也不計次數，實際用量會更低。

### 最壞情況

就算有人繞過應用程式上限（例如大量送無效請求，這類請求在 401 就結束），`--max-instances 1` 也把 CPU 鎖在 1 顆。整月滿載約 260 萬 vCPU 秒，扣掉免費額度，依 Tier 1 牌價（約 US$0.000024／vCPU 秒，上線前請核對）估算，**上限約 US$60／月**。

### 費用約束清單（上線前完成）

1. 在 GCP 帳單建立預算 **US$5／月**，並設定 50%、90%、100% 的 email 通知。已建立：帳單帳戶幣別是新台幣，所以設為 NT$150／月，範圍限 ga4-mcp-506714。
2. Cloud Run 設定 `--max-instances 1`、`--min-instances 0`、`--cpu-throttling`。
3. 應用程式上限維持預設，或調得更低：`SEO_PULSE_DAILY_TOTAL`、`SEO_PULSE_RATE_PER_DAY`。
4. 邀請名單控制人數。依每人每日 200 次計算，2,000 次的總上限大約可以支撐 10 位重度使用者同時用滿。
5. 要停止服務時：`gcloud run services update seo-pulse --max-instances 0`，或直接刪除服務。

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
