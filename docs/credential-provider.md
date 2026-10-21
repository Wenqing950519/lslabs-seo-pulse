# CredentialProvider：本機與雲端兩種憑證來源

`seo_pulse_mcp/connectors/credentials.py` 定義了 `CredentialProvider` 介面：

```python
class CredentialProvider(ABC):
    @abstractmethod
    def get(self, service: "gsc" | "ga4", context=None) -> Credentials: ...
```

`GoogleGSCConnector`／`GoogleGA4Connector` 建構時都能注入任何 `CredentialProvider`，並把 `credential_context` 傳進 `get()`。

## `LocalFileCredentialProvider`（本機 stdio 與本機 HTTP）

- 單一本機使用者，沿用 `~/.config/seo-pulse/tokens/`（或 `SEO_PULSE_TOKEN_DIR`）的快取 token；檔案權限、原子寫入、scope 必須完全相符等規則與 0.1.0 相同。
- `context` 一律是 `None`。
- 0.3.0 起整個程序共用同一個 provider（`local_provider()`）：
  - 有效的憑證留在記憶體，不再每次呼叫都重讀檔案；
  - 每個服務各有一把鎖，同時發生的呼叫不會重複刷新、重寫同一個 token 檔。

## `RemoteUserCredentialProvider`（雲端模式，0.3.0 實作）

- **`context` 是已驗證的 `Caller`**（`seo_pulse_mcp/caller.py`），內含 Google `sub` 與使用者的 Google refresh token。
  - 身分由 SEO Pulse 自己的 OAuth 授權端驗證（`seo_pulse_mcp/auth.py`）。
  - refresh token 放在加密的 bearer token 裡，伺服器端不保存。
- **快取**：Google 短期存取權杖以 refresh token 的 SHA-256 為鍵，存在記憶體。
  - 每位使用者一把鎖，同時發生的呼叫只會刷新一次。
  - 登入當下 Google 回傳的存取權杖會先放進快取（`prime`），第一次呼叫工具時不必再刷新。
- **不做互動登入**：找不到授權或授權已被撤銷時，回傳繁中錯誤，請使用者在 AI App 重新連線。
- **註冊位置**：雲端模式啟動時由 `configure_remote_provider()` 註冊。`get_connectors()` 偵測到目前有 `Caller` 時就改用這個 provider，並且不再退回任何環境變數預設值，所以 `site_url`／`property_id` 必須由工具參數提供。

部署、金鑰輪替與撤銷方式見 [hosting.md](hosting.md)。

> 2026-10-21 第一版（0.2.0）把這裡寫成「第二階段規劃：OAuth proxy + 資料庫加密保存 refresh token」。0.3.0 改成無狀態設計：授權端內建於伺服器，refresh token 由 AI App 保管的加密憑證攜帶。原規劃已被本文件取代。
