"""Credential provider abstraction for Google connectors.

This phase only ships `LocalFileCredentialProvider`: a single local user's cached
OAuth token under `~/.config/seo-pulse/tokens` (or `SEO_PULSE_TOKEN_DIR`), with the
exact file layout, permissions (0o700 dirs, atomic write, owner-only file) and error
messages as seo-pulse 0.1.0. `context` is accepted by `CredentialProvider.get()` but
always `None` in this phase — connectors never receive a per-caller identity yet.

Phase 2 (not implemented here, planning note only): a `RemoteUserCredentialProvider`
would be handed a non-None `context` identifying the calling user. That identity would
already be verified by an OAuth proxy sitting in front of this MCP server (the proxy
validates the ChatGPT/OAuth 2.1 bearer token before the request ever reaches
`CredentialProvider.get()`). The provider would then look up that user's Google
refresh token from encrypted storage (e.g. a database or KMS-backed secret store,
keyed by the verified identity), refresh it if expired, and return `Credentials` —
never prompting or opening an interactive browser flow, since that only makes sense
for the local single-user case. See `docs/credential-provider.md`.
"""
import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

GSC_SCOPES = ("https://www.googleapis.com/auth/webmasters.readonly",)
GA4_SCOPES = ("https://www.googleapis.com/auth/analytics.readonly",)
AUTH_REQUIRED = "Google 授權無效或尚未設定，請先執行 seo-pulse auth。"


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
    """service: "gsc" or "ga4"; context: reserved for a per-request caller identity.

    Always `None` in this phase — see the module docstring for the phase 2 plan.
    """

    @abstractmethod
    def get(self, service, context=None):
        ...


class LocalFileCredentialProvider(CredentialProvider):
    """Default provider: the same single-local-user token cache as 0.1.0."""

    def get(self, service, context=None):
        return _credentials(service)
