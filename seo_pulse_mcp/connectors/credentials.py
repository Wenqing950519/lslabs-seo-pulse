"""Credential provider abstraction for Google connectors.

`LocalFileCredentialProvider` serves a single local user's cached OAuth token under
`~/.config/seo-pulse/tokens` (or `SEO_PULSE_TOKEN_DIR`), preserving the file layout,
atomic writes and owner-only permissions. Local calls have no caller context.

`RemoteUserCredentialProvider` serves the hosted server: `context` is the verified
`Caller` (see seo_pulse_mcp.caller) whose Google refresh token arrived inside the
encrypted bearer token. It never prompts and never writes to disk; short-lived Google
access tokens are cached in memory per refresh token, with one lock per caller so
concurrent calls refresh once. See `docs/credential-provider.md`.
"""
import hashlib
import json
import os
import tempfile
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

GSC_SCOPES = ("https://www.googleapis.com/auth/webmasters.readonly",)
GA4_SCOPES = ("https://www.googleapis.com/auth/analytics.readonly",)
AUTH_REQUIRED = "Google 授權無效或尚未設定，請先執行 seo-pulse auth。"
REMOTE_AUTH_REQUIRED = "Google 授權已失效或被撤銷，請在 AI App 中移除 SEO Pulse 連線後重新連線。"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _save_token(path, credentials):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Atomic replacement with owner-only permissions, including existing caches.
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(credentials.to_json())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _credentials(service, *, interactive=False):
    scopes = {"gsc": GSC_SCOPES, "ga4": GA4_SCOPES}[service]
    path = Path(os.environ.get("SEO_PULSE_TOKEN_DIR", "~/.config/seo-pulse/tokens")).expanduser() / f"{service}.json"
    credentials = None
    if path.is_file():
        try:
            # Check stored grants before loading: never reuse broader scopes.
            info = json.loads(path.read_text(encoding="utf-8"))
            if set(info.get("scopes", [])) == set(scopes):
                credentials = Credentials.from_authorized_user_info(info, scopes=list(scopes))
        except (ValueError, KeyError):
            credentials = None
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            _save_token(path, credentials)
        except RefreshError:
            credentials = None
    if credentials and credentials.valid:
        return credentials
    if not interactive:
        raise RuntimeError(AUTH_REQUIRED)
    secret = os.environ.get("SEO_PULSE_GOOGLE_CLIENT_SECRET")
    if not secret or not Path(secret).expanduser().is_file():
        raise RuntimeError("請設定 SEO_PULSE_GOOGLE_CLIENT_SECRET，指向 repo 外的 OAuth Desktop client_secret JSON 檔案。")
    flow = InstalledAppFlow.from_client_secrets_file(str(Path(secret).expanduser()), scopes=list(scopes))
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _save_token(path, credentials)
    return credentials


def authenticate():
    """Interactive entry point called only by the explicit auth CLI command."""
    for service in ("gsc", "ga4"):
        _credentials(service, interactive=True)


class CredentialProvider(ABC):
    """service: "gsc" or "ga4"; context: verified hosted Caller, or None locally."""

    @abstractmethod
    def get(self, service, context=None):
        ...


class LocalFileCredentialProvider(CredentialProvider):
    """Default provider: the same single-local-user token files as 0.1.0.

    Valid credentials stay in memory, and one lock per service keeps concurrent
    calls from refreshing (and rewriting) the same token file at once.
    """

    _locks = {"gsc": threading.Lock(), "ga4": threading.Lock()}

    def __init__(self):
        self._cache = {}

    def get(self, service, context=None):
        key = (service, os.environ.get("SEO_PULSE_TOKEN_DIR"))
        with self._locks[service]:
            credentials = self._cache.get(key)
            if not getattr(credentials, "valid", False):
                credentials = self._cache[key] = _credentials(service)
            return credentials


_local_provider = LocalFileCredentialProvider()


def local_provider():
    """Shared so the in-memory cache and locks span connector instances."""
    return _local_provider


class RemoteUserCredentialProvider(CredentialProvider):
    """Per-caller Google credentials for the hosted server (one grant covers GSC and GA4)."""

    MAX_CACHED = 1000

    def __init__(self, client_id, client_secret, *, credentials_factory=Credentials,
                 request_factory=Request, token_uri=GOOGLE_TOKEN_URI):
        self._client_id, self._client_secret = client_id, client_secret
        self._factory, self._request_factory, self._token_uri = credentials_factory, request_factory, token_uri
        self._guard = threading.Lock()
        self._locks = {}
        self._cache = {}

    @staticmethod
    def _key(refresh_token):
        return hashlib.sha256(refresh_token.encode()).hexdigest()

    def _lock_for(self, key):
        with self._guard:
            if len(self._cache) > self.MAX_CACHED:
                for stale in [k for k, c in self._cache.items() if not c.valid]:
                    self._cache.pop(stale, None)
                    self._locks.pop(stale, None)
            return self._locks.setdefault(key, threading.Lock())

    def _new(self, refresh_token, token=None):
        return self._factory(token=token, refresh_token=refresh_token, token_uri=self._token_uri,
                             client_id=self._client_id, client_secret=self._client_secret)

    def prime(self, refresh_token, access_token, expires_in):
        """Reuse the access token Google returned at sign-in instead of refreshing at once."""
        credentials = self._new(refresh_token, token=access_token)
        # google-auth compares expiry as naive UTC.
        credentials.expiry = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in) - 60)).replace(tzinfo=None)
        key = self._key(refresh_token)
        with self._lock_for(key):
            self._cache[key] = credentials

    def forget(self, refresh_token):
        key = self._key(refresh_token)
        with self._guard:
            self._cache.pop(key, None)

    def get(self, service, context=None):
        if context is None or not getattr(context, "google_refresh_token", None):
            raise RuntimeError(REMOTE_AUTH_REQUIRED)
        key = self._key(context.google_refresh_token)
        with self._lock_for(key):
            credentials = self._cache.get(key)
            if credentials is None or not credentials.valid:
                credentials = self._new(context.google_refresh_token)
                try:
                    credentials.refresh(self._request_factory())
                except RefreshError:
                    raise RuntimeError(REMOTE_AUTH_REQUIRED) from None
                self._cache[key] = credentials
            return credentials


_remote_provider = None


def configure_remote_provider(provider):
    """Installed by the hosted server at startup; connectors use it for every Caller."""
    global _remote_provider
    _remote_provider = provider


def remote_provider():
    if _remote_provider is None:
        raise RuntimeError("雲端模式尚未設定 Google Web OAuth client。")
    return _remote_provider
