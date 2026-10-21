"""Hosted (cloud) mode: the same tools behind OAuth, for ChatGPT and other web AI apps.

Enabled by SEO_PULSE_PUBLIC_URL. Configuration is environment-only so it maps onto
Cloud Run env vars and secrets; see docs/hosting.md for every variable and the
deployment and cost-limit steps.
"""
import json
import os
import sys
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .auth import (CALLBACK_PATH, SCOPE, AccessPolicy, StatelessOAuthProvider, TokenCodec)
from .branding import WEBSITE_URL

DEFAULT_REDIRECT_HOSTS = ("chatgpt.com", "chat.openai.com", "claude.ai", "claude.com")
DEFAULT_ORIGINS = ("https://chatgpt.com", "https://chat.openai.com", "https://claude.ai")
LANDING = f"{WEBSITE_URL}?utm_source=seo-pulse&utm_medium=server&utm_campaign=mcp-root"


def _list(value):
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def _int(env, name, default):
    try:
        return int(env.get(name) or default)
    except ValueError:
        raise ValueError(f"{name} 必須是整數，目前是：{env.get(name)}") from None


def _verification_files(value):
    """`/path=content` pairs (comma-separated) served as text/plain, e.g. a domain challenge token."""
    files = {}
    for item in _list(value):
        path, _, content = item.partition("=")
        if not path.startswith("/") or not content:
            raise ValueError("SEO_PULSE_VERIFICATION_FILES 格式：/路徑=內容，多筆以逗號分隔。")
        files[path] = content
    return files


@dataclass(frozen=True)
class HostedConfig:
    public_url: str
    google_client_id: str
    google_client_secret: str = field(repr=False)
    token_keys: tuple = field(repr=False)
    access_policy: AccessPolicy
    redirect_hosts: tuple = DEFAULT_REDIRECT_HOSTS
    allowed_hosts: tuple = ()
    allowed_origins: tuple = DEFAULT_ORIGINS
    verification_files: dict = field(default_factory=dict)
    per_minute: int = 20
    per_day: int = 200
    daily_total: int = 2000
    cache_seconds: int = 900
    max_concurrency: int = 8

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        public_url = (env.get("SEO_PULSE_PUBLIC_URL") or "").strip().rstrip("/")
        parsed = urlparse(public_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path not in ("", "/"):
            raise ValueError("SEO_PULSE_PUBLIC_URL 必須是 https:// 開頭、不含路徑的網址，例如 https://pulse.lslabs.tw。")
        missing = [name for name in ("SEO_PULSE_GOOGLE_WEB_CLIENT_ID", "SEO_PULSE_GOOGLE_WEB_CLIENT_SECRET",
                                     "SEO_PULSE_TOKEN_KEYS") if not env.get(name)]
        if missing:
            raise ValueError(f"雲端模式缺少設定：{', '.join(missing)}。")
        emails, domains = _list(env.get("SEO_PULSE_ALLOWED_EMAILS")), _list(env.get("SEO_PULSE_ALLOWED_EMAIL_DOMAINS"))
        open_signup = env.get("SEO_PULSE_OPEN_SIGNUP") == "1"
        if not (emails or domains or open_signup):
            raise ValueError("請設定 SEO_PULSE_ALLOWED_EMAILS 或 SEO_PULSE_ALLOWED_EMAIL_DOMAINS（邀請名單）；"
                             "確定要開放所有 Google 帳號時才設 SEO_PULSE_OPEN_SIGNUP=1。")
        return cls(
            public_url=public_url,
            google_client_id=env["SEO_PULSE_GOOGLE_WEB_CLIENT_ID"],
            google_client_secret=env["SEO_PULSE_GOOGLE_WEB_CLIENT_SECRET"],
            token_keys=_list(env["SEO_PULSE_TOKEN_KEYS"]),
            access_policy=AccessPolicy(emails, domains, open_signup),
            redirect_hosts=_list(env.get("SEO_PULSE_ALLOWED_REDIRECT_HOSTS")) or DEFAULT_REDIRECT_HOSTS,
            allowed_hosts=_list(env.get("SEO_PULSE_ALLOWED_HOSTS")),
            allowed_origins=DEFAULT_ORIGINS + _list(env.get("SEO_PULSE_ALLOWED_ORIGINS")),
            verification_files=_verification_files(env.get("SEO_PULSE_VERIFICATION_FILES")),
            per_minute=_int(env, "SEO_PULSE_RATE_PER_MINUTE", 20),
            per_day=_int(env, "SEO_PULSE_RATE_PER_DAY", 200),
            daily_total=_int(env, "SEO_PULSE_DAILY_TOTAL", 2000),
            cache_seconds=_int(env, "SEO_PULSE_CACHE_SECONDS", 900),
            max_concurrency=_int(env, "SEO_PULSE_MAX_CONCURRENCY", 8),
        )

    @property
    def host(self):
        return urlparse(self.public_url).hostname


def build_app(config, http_transport=None):
    """Starlette app: MCP at /mcp behind OAuth, plus discovery, callback and plain routes."""
    from mcp.server.auth.handlers.metadata import MetadataHandler, ProtectedResourceMetadataHandler
    from mcp.server.auth.routes import build_metadata, cors_middleware
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from mcp.server.transport_security import TransportSecuritySettings
    from mcp.shared.auth import ProtectedResourceMetadata
    from pydantic import AnyHttpUrl
    from starlette.responses import PlainTextResponse, RedirectResponse
    from starlette.routing import Route

    from . import server
    from .connectors.credentials import RemoteUserCredentialProvider, configure_remote_provider
    from .runtime import ToolRuntime

    credentials = RemoteUserCredentialProvider(config.google_client_id, config.google_client_secret)
    configure_remote_provider(credentials)
    runtime = ToolRuntime(max_concurrency=config.max_concurrency, per_minute=config.per_minute,
                          per_day=config.per_day, daily_total=config.daily_total, cache_seconds=config.cache_seconds)
    provider = StatelessOAuthProvider(
        public_url=config.public_url, google_client_id=config.google_client_id,
        google_client_secret=config.google_client_secret, codec=TokenCodec(config.token_keys),
        access_policy=config.access_policy, redirect_hosts=config.redirect_hosts,
        credentials=credentials, http_transport=http_transport)
    registration = ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE])
    revocation = RevocationOptions(enabled=True)
    auth = AuthSettings(issuer_url=AnyHttpUrl(config.public_url), resource_server_url=AnyHttpUrl(provider.resource_url),
                        required_scopes=[SCOPE], client_registration_options=registration,
                        revocation_options=revocation, service_documentation_url=AnyHttpUrl(WEBSITE_URL),
                        validate_token_resource=True)
    host = config.host
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host, f"{host}:*", *config.allowed_hosts],
        allowed_origins=[config.public_url, *config.allowed_origins])
    mcp = server.build_mcp(runtime, auth_server_provider=provider, auth=auth, transport_security=security)

    # The SDK's metadata omits "none"; ChatGPT registers as a public PKCE client.
    metadata = build_metadata(AnyHttpUrl(config.public_url), AnyHttpUrl(WEBSITE_URL), registration, revocation)
    metadata.token_endpoint_auth_methods_supported = ["none", "client_secret_post", "client_secret_basic"]
    resource_metadata = ProtectedResourceMetadata(
        resource=AnyHttpUrl(provider.resource_url), authorization_servers=[AnyHttpUrl(config.public_url)],
        scopes_supported=[SCOPE], resource_name="SEO Pulse", resource_documentation=AnyHttpUrl(WEBSITE_URL))

    async def landing(request):
        return RedirectResponse(LANDING, 302)

    async def health(request):
        return PlainTextResponse("ok")

    def text_file(content):
        async def serve_file(request):
            return PlainTextResponse(content)
        return serve_file

    app = mcp.streamable_http_app()
    as_metadata = Route("/.well-known/oauth-authorization-server",
                        endpoint=cors_middleware(MetadataHandler(metadata).handle, ["GET", "OPTIONS"]),
                        methods=["GET", "OPTIONS"])
    app.router.routes[:] = [as_metadata if getattr(r, "path", None) == as_metadata.path else r
                            for r in app.router.routes]
    app.router.routes.extend([
        Route("/", landing, methods=["GET"]),
        # Cloud Run reserves paths ending in "z" (its front end answers /healthz itself).
        Route("/health", health, methods=["GET"]),
        Route(CALLBACK_PATH, provider.google_callback, methods=["GET"]),
        # Root alias of the RFC 9728 document the SDK serves at /.well-known/oauth-protected-resource/mcp.
        Route("/.well-known/oauth-protected-resource",
              endpoint=cors_middleware(ProtectedResourceMetadataHandler(resource_metadata).handle, ["GET", "OPTIONS"]),
              methods=["GET", "OPTIONS"]),
        *[Route(path, text_file(content), methods=["GET"]) for path, content in config.verification_files.items()],
    ])
    return app


def uvicorn_config(app, host, port, hosted=False):
    """No `server` header; in hosted mode no access log (query strings carry OAuth codes)
    and trust the Cloud Run front end's X-Forwarded-* headers."""
    import uvicorn
    return uvicorn.Config(app, host=host, port=port, server_header=False, log_level="info",
                          access_log=not hosted, proxy_headers=hosted,
                          forwarded_allow_ips="*" if hosted else None)


def run_hosted(config, host, port):
    import uvicorn
    host = "0.0.0.0" if host == "127.0.0.1" and os.environ.get("K_SERVICE") else host
    summary = {"public_url": config.public_url, "host": host, "port": port, "per_minute": config.per_minute,
               "per_day": config.per_day, "daily_total": config.daily_total, "cache_seconds": config.cache_seconds}
    print("SEO Pulse 雲端模式啟動：" + json.dumps(summary, ensure_ascii=False), file=sys.stderr)
    uvicorn.Server(uvicorn_config(build_app(config), host, port, hosted=True)).run()

