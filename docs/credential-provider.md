# CredentialProvider：第二階段規劃（只寫說明，本階段不實作）

`seo_pulse_mcp/connectors/credentials.py` 定義了 `CredentialProvider` 介面：

```python
class CredentialProvider(ABC):
    @abstractmethod
    def get(self, service: "gsc" | "ga4", context=None) -> Credentials: ...
```

本階段只有 `LocalFileCredentialProvider`：單一本機使用者、沿用 `~/.config/seo-pulse/tokens/`
（或 `SEO_PULSE_TOKEN_DIR`）裡的快取 token，行為與 0.1.0 完全一致。`GoogleGSCConnector`／
`GoogleGA4Connector` 建構時可注入任何 `CredentialProvider`，`context` 參數目前一律是 `None`。

## 第二階段：`RemoteUserCredentialProvider`（預計怎麼接，尚未實作）

1. **身分驗證在 MCP 伺服器之外完成**：ChatGPT 或其他遠端用戶端先經過一個 OAuth proxy（自建或代管
   IdP）完成 OAuth 2.1 + PKCE 流程，proxy 核發的 bearer token 會附帶已驗證的使用者身分。
2. **每次請求帶入使用者 context**：MCP 的 request context（或 HTTP 中介層）把驗證過的使用者
   識別碼傳入 `get(service, context)` 的 `context` 參數；`RemoteUserCredentialProvider.get()`
   只依賴這個已驗證身分查找，不會自己發起登入或信任使用者自稱的身分。
3. **依使用者加密保存 refresh token**：每位使用者的 Google refresh token 存在資料庫或 KV，
   以 KMS 或等效金鑰加密；`get()` 解密、檢查到期時間，過期才用 `google.auth.transport.requests.Request`
   刷新並寫回加密儲存。
4. **沒有互動登入流程**：`LocalFileCredentialProvider` 在沒有有效 token 時可以跑
   `InstalledAppFlow.run_local_server()`（桌面瀏覽器登入）；`RemoteUserCredentialProvider`
   不會這麼做——使用者的 Google 授權是在加入雲端版時，透過另一個獨立的 Web OAuth 流程完成的，
   `get()` 只負責讀取已經存在的授權，找不到就回傳清楚的錯誤，不會自己開瀏覽器。
5. **錯誤處理**：找不到對應使用者的 token、token 被撤銷、或 context 缺少身分時，一律回傳與
   `LocalFileCredentialProvider` 風格一致的繁中錯誤訊息，不洩漏其他使用者的任何資訊。

本文件只是規劃；Google Web OAuth client、使用者 token 儲存、OAuth proxy、資料庫／KV 都尚未建立，
也不在本階段範圍內（見交接規格第 2.5 節「本階段明確不做」）。
