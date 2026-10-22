# 雲端版監控手冊（給監控代理與值班者）

本文件說明 SEO Pulse 雲端版的後端組成、怎麼判斷它是否正常、要看哪些用量與費用、以及要在什麼情況發出警示。部署與設定步驟見 [hosting.md](hosting.md)。本文寫於 2026-10-21。`seo-pulse-00002-d9w` 是第一個上線版本，沒有 `/health` 與結構化事件；重新部署後才有這兩項，請以 `gcloud run services describe` 查到的最新版本為準。

2026-10-22 安全更新加入 Firestore 共享限制與授權碼防重放；以下行為需確認部署的是含此更新的 revision。先前只依賴記憶體的 revision 不具備相同保證。

## 1. 組成與位置

| 元件 | 位置 | 說明 |
|---|---|---|
| MCP 伺服器 | Cloud Run 服務 `seo-pulse`，專案 `ga4-mcp-506714`，區域 `asia-east1` | Python 0.3.0；容器映像在 Artifact Registry `asia-east1/cloud-run-source-deploy` |
| 對外網址 | `https://pulse.lslabs.tw`（MCP 端點 `/mcp`） | Cloud Run 網域對應，DNS 在 Cloudflare：`pulse` CNAME `ghs.googlehosted.com`，必須是 DNS only |
| 備用網址 | `https://seo-pulse-626389044762.asia-east1.run.app`、`https://seo-pulse-h7lv7s4yaa-de.a.run.app` | 直接打到 Cloud Run，適合在網域或憑證出問題時區分故障點。`/mcp` 只接受 `pulse.lslabs.tw` 的 Host：沒帶憑證時先被認證擋下回 401，帶有效憑證則回 421 |
| 機密 | Secret Manager（專案 `ga4-mcp-506714`）：`seo-pulse-token-keys`、`seo-pulse-google-secret`、`seo-pulse-state-hmac` | 依序用於加密憑證、Google OAuth、共享紀錄的 HMAC。**監控代理不應有讀取權** |
| 共享安全狀態 | Firestore Native `(default)`、`asia-east1`，專案 `ga4-mcp-506714`，collection `seo_pulse_state` | 全站與個人用量、已兌換授權碼 HMAC；`expire_at` TTL 清除。不保存 Google token、原始帳號識別或報表 |
| Google 登入 | 專案 `lslabs-seo-pulse`：同意畫面品牌「SEO Pulse」、網頁應用程式 client「SEO Pulse cloud」 | 外部、正式版、未驗證。Search Console、GA4 Data、Analytics Admin API 的配額都算在這個專案 |
| 產品頁 | `https://lslabs.tw/seo-pulse/`、`/privacy/`、`/terms/` | Cloudflare Pages（home repo） |
| 費用通知 | 帳單帳戶預算「SEO Pulse cloud (ga4-mcp-506714)」NT$150／月 | 用到 50%、90%、100% 時寄 email 給帳單管理員 |

## 2. 一次請求怎麼走

1. ChatGPT 讀 `/.well-known/oauth-protected-resource` 與 `/.well-known/oauth-authorization-server`，用 `POST /register` 做動態註冊。
2. 使用者被導到 `GET /authorize`，再轉到 Google 登入；Google 回到 `GET /oauth/google/callback`。
3. 伺服器在這一步檢查三件事：email 在邀請名單、四個唯讀範圍都有授權、拿到 refresh token。通過後把 Google 授權加密成授權碼，轉回 ChatGPT。
4. ChatGPT 用 `POST /token` 兌換授權碼；Firestore 原子登記成功後才發出存取憑證（1 小時）與更新憑證（30 天，使用時輪替）。其他程序或新 revision 也不能重複兌換同一碼。
5. 之後每次工具呼叫都是 `POST /mcp`，帶 `Authorization: Bearer …`。伺服器在記憶體解密憑證並檢查邀請名單；若命中 15 分鐘結果快取，確認 Firestore 可用後回傳。未命中則在共享交易中檢查並扣除每人每分鐘、每人每日、全站每日額度，成功後才在背景執行緒呼叫 Google API。

重啟只清空結果快取與 Google 短期權杖；共享用量與授權碼紀錄保留，已發出的連線憑證仍依效期與邀請名單驗證。全站及每位使用者各一筆計數跨日覆寫，TTL 到期時間為該 UTC 日結束後 24 小時；授權碼摘要到期時間為授權碼到期後 60 秒。TTL 清除通常在到期後 24 小時內完成，不參與授權有效性判定。細節見 hosting.md。

## 3. 健康檢查

建議每 5 分鐘檢查一次。

| 檢查 | 指令 | 正常結果 |
|---|---|---|
| 共享儲存可用性 | `curl --max-time 12 -s -o /dev/null -w "%{http_code}" https://pulse.lslabs.tw/health` | 200、內容 `ok`；唯讀 Firestore 交易，不扣額度、不呼叫 Google |
| OAuth 探索文件 | `curl -s https://pulse.lslabs.tw/.well-known/oauth-protected-resource` | 200，JSON 的 `resource` 是 `https://pulse.lslabs.tw/mcp` |
| 授權伺服器 metadata | `curl -s https://pulse.lslabs.tw/.well-known/oauth-authorization-server` | 200，`code_challenge_methods_supported` 含 `S256`，並有 `registration_endpoint` |
| 認證閘門 | `curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d "{}" https://pulse.lslabs.tw/mcp` | 401，回應標頭 `WWW-Authenticate` 含 `resource_metadata=` |
| 首頁導流 | `curl -s -o /dev/null -w "%{redirect_url}" https://pulse.lslabs.tw/` | 302 到 `https://lslabs.tw/seo-pulse/?utm_source=seo-pulse&utm_medium=server&utm_campaign=mcp-root` |
| 憑證 | `curl -sv https://pulse.lslabs.tw/ 2>&1 \| grep expire` | 剩餘有效天數 > 14（Google 會自動續期） |
| 網域對應 | `gcloud beta run domain-mappings describe --domain pulse.lslabs.tw --region asia-east1 --project ga4-mcp-506714` | `Ready: True`、`CertificateProvisioned: True` |
| 服務版本 | `gcloud run services describe seo-pulse --region asia-east1 --project ga4-mcp-506714 --format="value(status.latestReadyRevisionName)"` | 跟上次記錄相同；改變就代表有人重新部署 |

新版本 `/health` 在 Firestore 失效或等待超過 8 秒時回 503。OAuth 探索文件成功只代表 HTTP 可用，不能取代此檢查。Cloud Run 前端會攔截 `/healthz`，因此使用 `/health`。冷啟動時間需另外納入外部監控的逾時設定。

**判斷故障點**：同一項檢查改打備用的 `run.app` 網址（`/mcp` 例外，見下）。

- `run.app` 正常、`pulse.lslabs.tw` 失敗：問題在 DNS、網域對應或憑證。
- 兩個都失敗：問題在服務本身。
- `/mcp` 的認證閘門檢查在兩種網址都回 401，可以照用；但帶有效憑證的實際工具呼叫只能走 `pulse.lslabs.tw`。

## 4. 上限一覽

| 層級 | 上限 | 設定位置 | 看得到嗎 |
|---|---|---|---|
| 每位使用者 | 每分鐘 20 次、每日 200 次，跨程序／revision 共用 | 環境變數 `SEO_PULSE_RATE_PER_MINUTE`、`SEO_PULSE_RATE_PER_DAY` | Firestore 文件與結構化事件；監控不需直接取得使用者紀錄 |
| 全站 | 每日 2,000 次，跨程序／revision 共用 | `SEO_PULSE_DAILY_TOTAL` | 事件的 `day_total` |
| 結果快取 | 相同使用者、工具、參數 900 秒內不再呼叫 Google，也不計次數 | `SEO_PULSE_CACHE_SECONDS` | `outcome=cached` 事件 |
| 同時執行 | 每個程序 8 個工具，不是跨實例總併發 | `SEO_PULSE_MAX_CONCURRENCY` | 程序設定 |
| Cloud Run | 最多 1 台、每台同時 20 個請求、1 vCPU、512 MiB、逾時 120 秒、只在處理請求時計 CPU、閒置時 0 台 | 服務設定 | `gcloud run services describe` |
| Google 使用者人數 | 驗證前整個專案生命週期最多 100 位使用者 | Google Auth Platform → 目標對象 | 只能在 Console 看 |
| Google 授權次數 | 每日 10,000 次 | Google Auth Platform → 總覽 | 只能在 Console 看 |
| Search Console API | 每個網站與每位使用者各 1,200 QPM；專案 40,000 QPM、30,000,000 QPD | Google | Monitoring 指標（見第 5 節） |
| GA4 Data API | 每個資源每日 200,000 token、每小時 40,000；同一專案對同一資源每小時 14,000 | Google，主要算在**使用者自己的 GA4 資源** | 同上 |

應用程式的每日計數以 UTC 日界線重置，也就是台灣時間每天 08:00。

共享限制依賴相同專案、資料庫、namespace 與 HMAC key。更改 namespace／key 會改變文件識別，不可當成一般版本輪替；舊記憶體版 revision 也必須停止接流量。Firestore 失效時新工具、快取讀取與授權碼兌換都會拒絕，沒有記憶體 fallback。單次工具可包含多個 Google API 呼叫，故工具額度不是 API 或帳單的硬上限。

## 5. 用量與費用

### Cloud Run 用量（專案 `ga4-mcp-506714`）

用 Cloud Monitoring API 讀。監控代理需要 `roles/monitoring.viewer`。

| 指標 | 意義 | 每月免費額度 |
|---|---|---|
| `run.googleapis.com/request_count` | 請求數，可依 `response_code_class` 分組（2xx／4xx／5xx） | 200 萬次 |
| `run.googleapis.com/request_latencies` | 延遲分布 | — |
| `run.googleapis.com/container/cpu/allocation_time` | 已分配 vCPU 秒 | 180,000 |
| `run.googleapis.com/container/memory/allocation_time` | 已分配 GiB 秒 | 360,000 |
| `run.googleapis.com/container/billable_instance_time` | 計費的執行個體秒數 | — |
| `run.googleapis.com/container/instance_count` | 執行個體數 | 上限 1 |

範例：過去 24 小時依回應類別加總的請求數。

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" "https://monitoring.googleapis.com/v3/projects/ga4-mcp-506714/timeSeries?filter=metric.type%3D%22run.googleapis.com%2Frequest_count%22%20AND%20resource.labels.service_name%3D%22seo-pulse%22&interval.startTime=$(date -u -d '-1 day' +%Y-%m-%dT%H:%M:%SZ)&interval.endTime=$(date -u +%Y-%m-%dT%H:%M:%SZ)&aggregation.alignmentPeriod=86400s&aggregation.perSeriesAligner=ALIGN_SUM&aggregation.crossSeriesReducer=REDUCE_SUM&aggregation.groupByFields=metric.labels.response_code_class"
```

當月 vCPU 秒：把 `metric.type` 換成 `run.googleapis.com/container/cpu/allocation_time`，起點設為當月 1 日，並移除 `groupByFields`。

基準值：2026-10-21 上線當天、只有部署與登入測試時，24 小時內共 12 個請求（2xx 4、3xx 7、4xx 1），約 44 vCPU 秒、7 GiB 秒。

### Google API 用量（專案 `lslabs-seo-pulse`）

指標：`serviceruntime.googleapis.com/api/request_count`

- resource type：`consumed_api`
- 依 `resource.labels.service` 分組：`searchconsole.googleapis.com`、`analyticsdata.googleapis.com`、`analyticsadmin.googleapis.com`
- 依 `metric.labels.response_code_class` 分組
- 需要在這個專案有 `roles/monitoring.viewer`

這三個 API 都不收費，只有配額。持續出現 429 代表撞到配額；403 通常是使用者對該網站或資源沒有權限，屬於使用者端問題。

### 實際費用

- **目前能取得的**：
  - 預算通知 email：NT$75、NT$135、NT$150 時寄出。
  - Console「帳單 → 報表」，篩選專案 `ga4-mcp-506714`。
- **程式化讀取還沒設定**，有兩條路，都需要人工建立：
  1. **預算 Pub/Sub 通知**：預算會定期發布 `costAmount`（當期累計花費）到指定主題，監控代理訂閱即可，最即時。
  2. **帳單匯出到 BigQuery**：能查到每項服務的細項。
- **預期值**：Cloud Run、Secret Manager（3 個 secret）、Artifact Registry 與 Cloud Logging 依實際用量與免費額度核對。Firestore 計數約每工具 2 讀 2 寫，快取與健康檢查也讀取；TTL 刪除不適用免費用量，不保證 NT$0。
- **最壞情況**：先前單一 1 vCPU 滿載約 US$60 的估算只涵蓋 CPU，未涵蓋記憶體、請求、Firestore、網路與其他服務，不能當帳單上限；預算通知不會自動停機。

## 6. 網站流量（導流成效）

GA4 資源 `541769792`（lslabs.tw 主站；正式網域白名單只有 `lslabs.tw`）：

| 來源 | 怎麼辨識 |
|---|---|
| 週報頁尾點擊 | `sessionSource = seo-pulse`、`sessionMedium = report`、`sessionCampaignName = weekly-report`；`utm_content` 為 `cloud`（雲端版）或 `local`（本機版） |
| 有人直接開伺服器網址 | `sessionSource = seo-pulse`、`sessionMedium = server`、`sessionCampaignName = mcp-root` |
| 登入失敗頁的連結 | `sessionSource = seo-pulse`、`sessionMedium = oauth`、`sessionCampaignName = sign-in` |
| 產品頁本身 | `landingPage` 或 `pagePath` 以 `/seo-pulse/` 開頭，含 `/privacy/`、`/terms/` |

`utm_content` 在 GA4 Data API 的維度名稱是 `sessionManualAdContent`。

Search Console 屬性 `sc-domain:lslabs.tw`：用 `page` 篩選條件「包含 `/seo-pulse/`」，追蹤曝光、點擊與查詢字。

監控代理有兩種讀法：

- 用自己的服務帳戶，在 GA4 資源加「檢視者」、在 Search Console 加「受限使用者」，直接呼叫 API。
- 用本機版 SEO Pulse 的 `ga4_report`／`gsc_query`。

## 7. 日誌與目前的可觀測性缺口

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="seo-pulse"' --project ga4-mcp-506714 --freshness=1d --limit 50
```

- **平台請求日誌**（`run.googleapis.com/requests`）：每個 HTTP 請求一筆，含狀態碼、延遲與完整網址，Cloud Logging 預設保存 30 天。`/authorize` 與 `/oauth/google/callback` 的網址含 PKCE challenge、state 與 Google 授權碼；授權碼只能用一次、幾分鐘內失效。
- **應用程式日誌**（stderr）：
  - 啟動時一行設定摘要（`SEO Pulse 雲端模式啟動：{…}`）。
  - SDK 對每個請求一行 `Processing request of type …`。
  - 雲端模式關閉了 uvicorn access log，避免重複記錄含授權碼的網址。
  - 0.3.0 起（`seo_pulse_mcp/events.py`），每次雲端工具呼叫與每次 Google 登入回呼各寫一行 JSON，Cloud Logging 會轉成 `jsonPayload`，欄位見下表。

### 結構化事件

| `jsonPayload.event` | 欄位 | `outcome` 的值 |
|---|---|---|
| `tool_call` | `tool`、`outcome`、`subject`（使用者雜湊）、`duration_ms`、`day_total`（當日全站已用次數）、`error_type`、`limit` | `ok`；`cached`（命中快取，不計次）；`limited`（`limit` = `per_minute`／`per_day`／`daily_total`）；`error`（`error_type` 為例外類別，`ValueError` 是使用者參數錯誤） |
| `sign_in` | `outcome`、`subject` | `signed_in`、`not_invited`、`missing_scope`、`cancelled`、`expired_state`、`google_failed`、`no_refresh_token` |

- **`severity`**：
  - `INFO`：正常。
  - `WARNING`：撞上限、使用者參數錯誤、沒有受邀、少勾了權限、登入連結過期。
  - `ERROR`：Google API 或伺服器錯誤、Google 登入交換失敗、沒拿到 refresh token。
- **隱私**：事件不含工具參數、email 或任何憑證。日誌 `subject` 是 Google `sub` 加固定前綴後取 SHA-256 的前 12 碼；Firestore 文件另使用祕密金鑰 HMAC-SHA256，兩者不能視為相同識別。
- **本機版**：不寫這些事件。

查詢範例：

```bash
# 過去 24 小時的工具呼叫
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="seo-pulse" AND jsonPayload.event="tool_call"' --project ga4-mcp-506714 --freshness=1d --format="table(timestamp,jsonPayload.tool,jsonPayload.outcome,jsonPayload.error_type,jsonPayload.limit,jsonPayload.duration_ms,jsonPayload.day_total)"

# 錯誤與撞上限
gcloud logging read 'resource.labels.service_name="seo-pulse" AND jsonPayload.event="tool_call" AND severity>=WARNING' --project ga4-mcp-506714 --freshness=1d

# 登入漏斗
gcloud logging read 'resource.labels.service_name="seo-pulse" AND jsonPayload.event="sign_in"' --project ga4-mcp-506714 --freshness=7d --format="table(timestamp,jsonPayload.outcome,jsonPayload.subject)"
```

要做成長期圖表或警示，可以建立 log-based metric，例如以 `jsonPayload.event="tool_call"` 為篩選條件、`jsonPayload.outcome` 為標籤的計數指標。

**仍然看不到的**：

- 尚未有面向監控的個人即時計數端點；例行監控用事件的 `day_total` 與數量，不需擴大讀取 Firestore 使用者紀錄的權限；
- Google Auth Platform 的使用者總數，只能在 Console 看。

## 8. 警示門檻建議

| 等級 | 條件 | 可能原因 |
|---|---|---|
| 緊急 | 健康檢查連續 2 次失敗 | 服務掛掉、網域或憑證失效 |
| 緊急 | `/health` 503 或 `error_type=AdmissionUnavailable` 持續出現 | Firestore／IAM／連線故障或共享狀態等待逾時；工具會在 Google 呼叫前拒絕 |
| 緊急 | 5 分鐘內 5xx 佔比 > 5% | 程式錯誤、Google API 異常 |
| 緊急 | 收到預算 100% 通知 | 異常流量；先執行第 10 節的停用 |
| 注意 | 當日請求數 > 1,500（全站上限的 75%） | 使用量成長或被濫用 |
| 注意 | 當月 vCPU 秒 > 120,000 | 接近免費額度 |
| 注意 | Google 使用者數 > 80 | 接近未驗證上限 100，要送 Google 驗證 |
| 注意 | 服務版本與上次記錄不同 | 有人重新部署，確認是預期中的 |
| 注意 | `lslabs-seo-pulse` 的 Google API 429 持續出現 | 配額不足 |
| 資訊 | 憑證剩餘 < 14 天 | Google 通常會自動續期；若沒續期，檢查 DNS 是否仍是 DNS only |

## 9. 監控代理的權限（最小權限）

建議建立專用服務帳戶，只給以下角色：

| 專案／對象 | 角色 |
|---|---|
| `ga4-mcp-506714` | `roles/monitoring.viewer`、`roles/logging.viewer`、`roles/run.viewer` |
| `lslabs-seo-pulse` | `roles/monitoring.viewer` |
| 帳單帳戶 | `roles/billing.viewer`（只在要讀費用報表時） |
| GA4 資源 541769792 | 檢視者 |
| Search Console `sc-domain:lslabs.tw` | 受限使用者 |

**不要給**：`roles/secretmanager.secretAccessor`、`roles/run.admin`、`roles/run.developer`、`roles/editor`、`roles/owner`，也不要讓它讀 `~/.config/seo-pulse/`。拿到 `seo-pulse-token-keys` 等於能偽造任何使用者的連線憑證。

## 10. 處置（給人，不給監控代理）

- **立即停止對外服務**：在 ga4-mcp-506714 移除 `allUsers` 的 `roles/run.invoker`，之後所有請求都回 403。

  ```bash
  gcloud run services remove-iam-policy-binding seo-pulse --region asia-east1 --project ga4-mcp-506714 --member=allUsers --role=roles/run.invoker
  ```

- **讓所有已發出的連線憑證失效**：在 `seo-pulse-token-keys` 新增只含一把新金鑰的版本（用 `seo-pulse keygen` 產生），再部署新版本。所有使用者都要重新連線。
- **移除單一使用者**：從 `SEO_PULSE_ALLOWED_EMAILS` 拿掉 email，用 `gcloud run services update … --update-env-vars` 更新。下一個請求就會被拒。
- **使用者要撤銷自己的授權**：請對方到 Google 帳戶的第三方連線頁移除 SEO Pulse。
