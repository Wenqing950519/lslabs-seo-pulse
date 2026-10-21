"""Hosted-mode OAuth: SEO Pulse is its own authorization server, Google is the identity provider.

ChatGPT (or any MCP client) registers with us, signs the user in through Google, and gets
SEO Pulse tokens. Nothing is stored server-side:

- client registrations are HMAC-signed into the client_id itself (redirect URIs included);
- authorization codes, access tokens and refresh tokens are Fernet-encrypted blobs
  (AES-128-CBC + HMAC-SHA256) that carry the caller's Google refresh token;
- the AI client holds those blobs, and the server decrypts them in memory per request.

So there is no database to run or pay for, and no at-rest store of anyone's Google
grant. The trade-offs are documented in docs/hosting.md: issued refresh tokens cannot be
revoked one by one (revoking the grant at Google cuts all of them), and single-use
authorization codes are only enforced within one process.
"""
import base64
import hashlib
import hmac
import html
import json
import secrets
import threading
import time
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
                                      RefreshToken, RegistrationError, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import Field
from starlette.responses import HTMLResponse, RedirectResponse

from .branding import WEBSITE_URL
from .connectors.credentials import GA4_SCOPES, GSC_SCOPES

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_SCOPES = ("openid", "email", *GSC_SCOPES, *GA4_SCOPES)
READ_SCOPES = (*GSC_SCOPES, *GA4_SCOPES)
SCOPE = "seo-pulse.read"
CALLBACK_PATH = "/oauth/google/callback"
CONTACT = "me@lslabs.tw"

STATE_TTL = 600
CODE_TTL = 120
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400


class GoogleAccessToken(AccessToken):
    google_refresh_token: str = Field(repr=False)
    email: str | None = Field(default=None, repr=False)


class GoogleAuthorizationCode(AuthorizationCode):
    google_refresh_token: str = Field(repr=False)
    email: str | None = Field(default=None, repr=False)


class GoogleRefreshToken(RefreshToken):
    google_refresh_token: str = Field(repr=False)
    email: str | None = Field(default=None, repr=False)


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TokenCodec:
    """Seals payloads with the first key; opens with any key, so keys can be rotated."""

    def __init__(self, keys):
        if not keys:
            raise ValueError("請設定 SEO_PULSE_TOKEN_KEYS（可用 seo-pulse keygen 產生）。")
        fernets = [Fernet(key) for key in keys]
        self._fernet = MultiFernet(fernets)
        self._mac_keys = [hashlib.sha256(b"seo-pulse-client|" + _unb64(key)).digest() for key in keys]

    def seal(self, kind, payload, now=None):
        data = json.dumps({"k": kind, "iat": int(now or time.time()), **payload}, separators=(",", ":"))
        if now is None:
            return self._fernet.encrypt(data.encode()).decode()
        return self._fernet.encrypt_at_time(data.encode(), int(now)).decode()

    def unseal(self, kind, token, ttl):
        try:
            data = json.loads(self._fernet.decrypt(token.encode(), ttl=ttl))
        except (InvalidToken, ValueError, TypeError, AttributeError):
            return None
        return data if isinstance(data, dict) and data.get("k") == kind else None

    def sign(self, message, key_index=0):
        return _b64(hmac.new(self._mac_keys[key_index], message, hashlib.sha256).digest())

    def verify(self, message, signature):
        """Index of the key that made `signature`, or None."""
        for index in range(len(self._mac_keys)):
            if hmac.compare_digest(self.sign(message, index), signature):
                return index
        return None


class AccessPolicy:
    """Pilot invite list: exact emails and/or whole email domains; open only when configured so."""

    def __init__(self, emails=(), domains=(), open_signup=False):
        self.emails = {e.strip().lower() for e in emails if e.strip()}
        self.domains = {d.strip().lower().lstrip("@") for d in domains if d.strip()}
        self.open_signup = open_signup

    def allows(self, email):
        if self.open_signup:
            return True
        email = (email or "").lower()
        return email in self.emails or email.rpartition("@")[2] in self.domains


class _UsedCodes:
    """Authorization codes already exchanged in this process (they expire after CODE_TTL anyway)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._seen = {}

    def claim(self, code):
        digest, now = hashlib.sha256(code.encode()).hexdigest(), time.time()
        with self._lock:
            for key in [k for k, t in self._seen.items() if t < now]:
                del self._seen[key]
            if digest in self._seen:
                return False
            self._seen[digest] = now + CODE_TTL
            return True


def _page(status, title, body):
    """Plain page shown in the sign-in window when the flow cannot return to the AI app."""
    contact = f'<a href="mailto:{CONTACT}">{CONTACT}</a>'
    link = f'<a href="{WEBSITE_URL}?utm_source=seo-pulse&amp;utm_medium=oauth&amp;utm_campaign=sign-in">SEO Pulse 說明</a>'
    content = (f'<!doctype html><html lang="zh-Hant-TW"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}｜SEO Pulse</title>'
               f'<style>body{{font-family:system-ui,"Noto Sans TC",sans-serif;max-width:34rem;margin:15vh auto;'
               f'padding:0 16px;line-height:1.7;color:#111;background:#fff}}a{{color:#0b57d0}}</style></head>'
               f'<body><h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>'
               f'<p>問題請寄 {contact}。{link}</p></body></html>')
    return HTMLResponse(content, status_code=status, headers={"Cache-Control": "no-store"})


class StatelessOAuthProvider:
    """OAuthAuthorizationServerProvider for the MCP SDK; see the module docstring."""

    def __init__(self, *, public_url, google_client_id, google_client_secret, codec, access_policy,
                 redirect_hosts, credentials, http_transport=None):
        self.public_url = public_url.rstrip("/")
        self.resource_url = f"{self.public_url}/mcp"
        self.google_client_id, self.google_client_secret = google_client_id, google_client_secret
        self.codec, self.access_policy = codec, access_policy
        self.redirect_hosts = {h.lower() for h in redirect_hosts}
        self.credentials = credentials
        self._http_transport = http_transport
        self._used_codes = _UsedCodes()

    # --- client registration (RFC 7591), stateless --------------------------------

    def _redirect_allowed(self, uri):
        parsed = urlparse(str(uri))
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "http":
            return host in ("127.0.0.1", "localhost", "::1")
        return parsed.scheme == "https" and (host in self.redirect_hosts
                                             or any(host.endswith("." + h) for h in self.redirect_hosts))

    def _client_secret(self, client_id, key_index):
        return self.codec.sign(b"secret|" + client_id.encode(), key_index)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in client_info.redirect_uris or []]
        if not uris or not all(self._redirect_allowed(u) for u in uris):
            raise RegistrationError("invalid_redirect_uri",
                                    "redirect_uri 不在允許清單（ChatGPT、Claude 或本機 loopback）。")
        method = client_info.token_endpoint_auth_method or "client_secret_post"
        body = _b64(json.dumps({"u": uris, "m": method, "n": (client_info.client_name or "")[:60]},
                               separators=(",", ":"), ensure_ascii=False).encode())
        client_id = f"spc_{body}.{self.codec.sign(body.encode())}"
        # The SDK returns this same object to the client, so the stateless id and secret replace its random ones.
        client_info.client_id = client_id
        client_info.client_secret = None if method == "none" else self._client_secret(client_id, 0)
        client_info.client_secret_expires_at = None

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if not client_id.startswith("spc_") or "." not in client_id:
            return None
        body, _, signature = client_id[4:].rpartition(".")
        key_index = self.codec.verify(body.encode(), signature)
        if key_index is None:
            return None
        try:
            data = json.loads(_unb64(body))
        except ValueError:
            return None
        method = data.get("m", "client_secret_post")
        return OAuthClientInformationFull(
            client_id=client_id, redirect_uris=data["u"], token_endpoint_auth_method=method,
            client_secret=None if method == "none" else self._client_secret(client_id, key_index),
            grant_types=["authorization_code", "refresh_token"], response_types=["code"],
            client_name=data.get("n") or None, scope=SCOPE)

    # --- authorization: hand off to Google, come back with our own code -----------

    def _resource(self, requested):
        if requested and requested.rstrip("/") != self.resource_url:
            raise AuthorizeError("invalid_request", f"resource 必須是 {self.resource_url}")
        return self.resource_url

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        verifier = secrets.token_urlsafe(48)
        state = self.codec.seal("state", {
            "cid": client.client_id, "ru": str(params.redirect_uri), "rue": params.redirect_uri_provided_explicitly,
            "cc": params.code_challenge, "st": params.state, "sc": params.scopes or [SCOPE],
            "aud": self._resource(params.resource), "gv": verifier})
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        return GOOGLE_AUTH_URL + "?" + urlencode({
            "client_id": self.google_client_id, "redirect_uri": self.public_url + CALLBACK_PATH,
            "response_type": "code", "scope": " ".join(GOOGLE_SCOPES), "access_type": "offline",
            "prompt": "consent", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})

    async def _google_tokens(self, code, verifier):
        async with httpx.AsyncClient(timeout=15, transport=self._http_transport) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code, "client_id": self.google_client_id, "client_secret": self.google_client_secret,
                "redirect_uri": self.public_url + CALLBACK_PATH, "grant_type": "authorization_code",
                "code_verifier": verifier})
        if response.status_code != 200:
            return None
        return response.json()

    def _identity(self, tokens):
        """Claims of the ID token Google returned on this TLS exchange (OIDC Core 3.1.3.7)."""
        try:
            claims = jwt.decode(tokens.get("id_token", ""), options={"verify_signature": False})
        except jwt.PyJWTError:
            return None
        if claims.get("iss") not in GOOGLE_ISSUERS or claims.get("aud") != self.google_client_id:
            return None
        if not claims.get("sub") or not claims.get("email_verified"):
            return None
        return claims

    async def google_callback(self, request):
        query = request.query_params
        state = self.codec.unseal("state", query.get("state", ""), STATE_TTL)
        if state is None:
            return _page(400, "登入連結已失效", "這個登入連結已過期或無效，請回到 AI App 重新連線 SEO Pulse。")
        if query.get("error") or not query.get("code"):
            return RedirectResponse(construct_redirect_uri(state["ru"], error="access_denied",
                                                           error_description="Google 授權未完成", state=state["st"]), 302)
        tokens = await self._google_tokens(query["code"], state["gv"])
        claims = self._identity(tokens) if tokens else None
        if claims is None:
            return _page(502, "Google 登入失敗", "無法向 Google 完成登入，請稍後重試。")
        email = claims.get("email", "").lower()
        if not self.access_policy.allows(email):
            return _page(403, "尚未開放這個帳號",
                         f"SEO Pulse 雲端版目前採邀請制，{email} 不在試點名單。申請試用請寫信並附上要授權的 Google 帳號。")
        if not set(READ_SCOPES) <= set(tokens.get("scope", "").split()):
            return _page(400, "缺少必要權限",
                         "請在 Google 授權畫面同時勾選 Search Console 與 Google Analytics 的唯讀權限，再回到 AI App 重新連線。")
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return _page(502, "Google 未回傳授權", "Google 沒有回傳長期授權，請到 Google 帳戶的第三方連線移除 SEO Pulse 後重試。")
        self.credentials.prime(refresh_token, tokens.get("access_token"), tokens.get("expires_in", 0))
        code = self.codec.seal("code", {
            "cid": state["cid"], "ru": state["ru"], "rue": state["rue"], "cc": state["cc"], "sc": state["sc"],
            "aud": state["aud"], "sub": claims["sub"], "em": email, "grt": refresh_token})
        return RedirectResponse(construct_redirect_uri(state["ru"], code=code, state=state["st"]), 302)

    # --- token endpoint ------------------------------------------------------------

    async def load_authorization_code(self, client, authorization_code):
        data = self.codec.unseal("code", authorization_code, CODE_TTL)
        if data is None or data["cid"] != client.client_id:
            return None
        return GoogleAuthorizationCode(
            code=authorization_code, scopes=data["sc"], expires_at=data["iat"] + CODE_TTL, client_id=data["cid"],
            code_challenge=data["cc"], redirect_uri=data["ru"], redirect_uri_provided_explicitly=data["rue"],
            resource=data["aud"], subject=data["sub"], google_refresh_token=data["grt"], email=data.get("em"))

    def _issue(self, client_id, subject, refresh_token, scopes, resource, email):
        claims = {"cid": client_id, "sub": subject, "grt": refresh_token, "sc": scopes, "aud": resource, "em": email}
        return OAuthToken(access_token=self.codec.seal("at", claims), token_type="Bearer", expires_in=ACCESS_TTL,
                          scope=" ".join(scopes), refresh_token=self.codec.seal("rt", claims))

    async def exchange_authorization_code(self, client, authorization_code):
        if not self._used_codes.claim(authorization_code.code):
            raise TokenError("invalid_grant", "authorization code already used")
        return self._issue(client.client_id, authorization_code.subject, authorization_code.google_refresh_token,
                           authorization_code.scopes, authorization_code.resource, authorization_code.email)

    async def load_refresh_token(self, client, refresh_token):
        data = self.codec.unseal("rt", refresh_token, REFRESH_TTL)
        if data is None or data["cid"] != client.client_id or not self.access_policy.allows(data.get("em")):
            return None
        return GoogleRefreshToken(token=refresh_token, client_id=data["cid"], scopes=data["sc"],
                                  expires_at=data["iat"] + REFRESH_TTL, resource=data["aud"], subject=data["sub"],
                                  google_refresh_token=data["grt"], email=data.get("em"))

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        return self._issue(client.client_id, refresh_token.subject, refresh_token.google_refresh_token,
                           scopes, refresh_token.resource, refresh_token.email)

    async def load_access_token(self, token):
        data = self.codec.unseal("at", token, ACCESS_TTL)
        # Re-checking the invite list on every request makes removal take effect at once.
        if data is None or not self.access_policy.allows(data.get("em")):
            return None
        return GoogleAccessToken(token=token, client_id=data["cid"], scopes=data["sc"],
                                 expires_at=data["iat"] + ACCESS_TTL, resource=data["aud"], subject=data["sub"],
                                 google_refresh_token=data["grt"], email=data.get("em"))

    async def revoke_token(self, token):
        """Revoke the Google grant itself: every SEO Pulse token carrying it stops working."""
        refresh_token = getattr(token, "google_refresh_token", None)
        if not refresh_token:
            return
        self.credentials.forget(refresh_token)
        try:
            async with httpx.AsyncClient(timeout=10, transport=self._http_transport) as client:
                await client.post(GOOGLE_REVOKE_URL, data={"token": refresh_token})
        except httpx.HTTPError:
            pass
