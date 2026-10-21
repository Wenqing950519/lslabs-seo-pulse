"""Hosted mode: SEO Pulse is its own OAuth 2.1 authorization server with Google as the
identity provider, and keeps no server-side state (audit 2026-10-21 §3.A, §4)."""
import base64
import hashlib
import json
import secrets
import time
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient

from seo_pulse_mcp import server
from seo_pulse_mcp.auth import CODE_TTL, TokenCodec
from seo_pulse_mcp.caller import current_caller
from seo_pulse_mcp.hosting import HostedConfig, build_app, uvicorn_config

PUBLIC = "https://pulse.example.test"
CHATGPT_REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
KEY = Fernet.generate_key().decode()
SCOPES = ("openid https://www.googleapis.com/auth/userinfo.email "
          "https://www.googleapis.com/auth/webmasters.readonly https://www.googleapis.com/auth/analytics.readonly")


def config(**overrides):
    env = {"SEO_PULSE_PUBLIC_URL": PUBLIC, "SEO_PULSE_GOOGLE_WEB_CLIENT_ID": "google-cid",
           "SEO_PULSE_GOOGLE_WEB_CLIENT_SECRET": "google-secret", "SEO_PULSE_TOKEN_KEYS": KEY,
           "SEO_PULSE_ALLOWED_EMAILS": "invited@example.com", "SEO_PULSE_ALLOWED_HOSTS": "testserver",
           "SEO_PULSE_VERIFICATION_FILES": "/.well-known/openai-apps-challenge=challenge-token"}
    env.update(overrides)
    return HostedConfig.from_env(env)


def google_transport(email="invited@example.com", scope=SCOPES, refresh_token="google-rt"):
    def handler(request):
        assert request.url == httpx.URL("https://oauth2.googleapis.com/token")
        form = parse_qs(request.content.decode())
        assert form["code_verifier"][0] and form["client_secret"] == ["google-secret"]
        id_token = jwt.encode({"iss": "https://accounts.google.com", "aud": "google-cid", "sub": "google-sub-1",
                               "email": email, "email_verified": True, "exp": time.time() + 600}, "x", "HS256")
        body = {"access_token": "google-at", "expires_in": 3599, "scope": scope, "token_type": "Bearer",
                "id_token": id_token}
        if refresh_token:
            body["refresh_token"] = refresh_token
        return httpx.Response(200, json=body)
    return httpx.MockTransport(handler)


@pytest.fixture
def client_for():
    clients = []

    def make(cfg=None, transport=None):
        app = build_app(cfg or config(), http_transport=transport or google_transport())
        client = TestClient(app, base_url=PUBLIC.replace("https://pulse.example.test", "http://testserver"),
                            follow_redirects=False)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def register(client, redirect=CHATGPT_REDIRECT):
    return client.post("/register", json={"redirect_uris": [redirect], "token_endpoint_auth_method": "none",
                                          "grant_types": ["authorization_code", "refresh_token"],
                                          "response_types": ["code"], "client_name": "ChatGPT"})


def login(client):
    reg = register(client).json()
    verifier, challenge = pkce()
    auth = client.get("/authorize", params={"response_type": "code", "client_id": reg["client_id"],
                                            "redirect_uri": CHATGPT_REDIRECT, "code_challenge": challenge,
                                            "code_challenge_method": "S256", "state": "chatgpt-state",
                                            "resource": f"{PUBLIC}/mcp"})
    assert auth.status_code == 302
    google = urlparse(auth.headers["location"])
    assert google.netloc == "accounts.google.com"
    query = parse_qs(google.query)
    assert query["access_type"] == ["offline"] and query["code_challenge_method"] == ["S256"]
    assert "https://www.googleapis.com/auth/webmasters.readonly" in query["scope"][0].split()
    callback = client.get("/oauth/google/callback", params={"code": "google-code", "state": query["state"][0]})
    return reg, verifier, callback


def tokens(client):
    reg, verifier, callback = login(client)
    assert callback.status_code == 302
    back = urlparse(callback.headers["location"])
    params = parse_qs(back.query)
    assert f"{back.scheme}://{back.netloc}{back.path}" == CHATGPT_REDIRECT
    assert params["state"] == ["chatgpt-state"]
    token = client.post("/token", data={"grant_type": "authorization_code", "code": params["code"][0],
                                        "redirect_uri": CHATGPT_REDIRECT, "client_id": reg["client_id"],
                                        "code_verifier": verifier, "resource": f"{PUBLIC}/mcp"})
    assert token.status_code == 200, token.text
    return reg, params["code"][0], verifier, token.json()


MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, token=None, rid=1):
    headers = dict(MCP_HEADERS, **({"Authorization": f"Bearer {token}"} if token else {}))
    response = client.post("/mcp", headers=headers,
                           json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        data = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
        return response, json.loads(data[-1])
    return response, (response.json() if response.content else None)


# --- metadata the ChatGPT connector reads ---------------------------------------

def test_discovery_metadata(client_for):
    client = client_for()
    asm = client.get("/.well-known/oauth-authorization-server").json()
    assert asm["code_challenge_methods_supported"] == ["S256"]
    assert asm["registration_endpoint"] == f"{PUBLIC}/register"
    assert "none" in asm["token_endpoint_auth_methods_supported"]
    for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
        prm = client.get(path).json()
        assert prm["resource"] == f"{PUBLIC}/mcp"
        assert prm["authorization_servers"] == [f"{PUBLIC}/"]
    unauthorized, _ = rpc(client, "initialize")
    assert unauthorized.status_code == 401
    assert "resource_metadata=" in unauthorized.headers["www-authenticate"]


def test_plain_routes(client_for):
    client = client_for()
    assert client.get("/healthz").text == "ok"
    root = client.get("/")
    assert root.status_code == 302 and root.headers["location"].startswith("https://lslabs.tw/seo-pulse/?utm_")
    assert client.get("/.well-known/openai-apps-challenge").text == "challenge-token"


def test_uvicorn_hides_server_header_and_query_logs():
    cfg = uvicorn_config(object(), "0.0.0.0", 8080, hosted=True)
    assert cfg.server_header is False and cfg.access_log is False and cfg.proxy_headers


# --- full sign-in, then a tool call as that user --------------------------------

def test_sign_in_and_call_tool_as_user(client_for, monkeypatch):
    client = client_for()
    _, _, _, issued = tokens(client)
    assert issued["token_type"].lower() == "bearer" and issued["refresh_token"]
    assert "google-rt" not in issued["access_token"]

    seen = []
    monkeypatch.setattr(server, "get_connectors",
                        lambda *a, **k: (Mock(list_sites=lambda: seen.append(current_caller()) or []), Mock()))
    response, body = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                "clientInfo": {"name": "test", "version": "1"}},
                         token=issued["access_token"])
    assert response.status_code == 200, response.text
    assert body["result"]["serverInfo"]["websiteUrl"] == "https://lslabs.tw/seo-pulse/"
    _, listed = rpc(client, "tools/list", token=issued["access_token"], rid=2)
    assert {t["name"] for t in listed["result"]["tools"]} >= {"list_sites", "weekly_report", "list_ga4_properties"}
    _, called = rpc(client, "tools/call", {"name": "list_sites", "arguments": {}},
                    token=issued["access_token"], rid=3)
    assert not called["result"]["isError"], called
    assert seen[0].subject == "google-sub-1" and seen[0].google_refresh_token == "google-rt"


def test_authorization_code_is_single_use(client_for):
    client = client_for()
    reg, code, verifier, _ = tokens(client)
    again = client.post("/token", data={"grant_type": "authorization_code", "code": code,
                                        "redirect_uri": CHATGPT_REDIRECT, "client_id": reg["client_id"],
                                        "code_verifier": verifier})
    assert again.status_code == 400


def test_refresh_rotates_tokens(client_for):
    client = client_for()
    reg, _, _, issued = tokens(client)
    refreshed = client.post("/token", data={"grant_type": "refresh_token", "client_id": reg["client_id"],
                                            "refresh_token": issued["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["access_token"] != issued["access_token"]


def test_uninvited_account_gets_a_readable_page(client_for):
    client = client_for(transport=google_transport(email="stranger@example.com"))
    _, _, callback = login(client)
    assert callback.status_code == 403
    assert "me@lslabs.tw" in callback.text and "lslabs.tw/seo-pulse" in callback.text


def test_missing_readonly_scope_is_explained(client_for):
    client = client_for(transport=google_transport(scope="openid email"))
    _, _, callback = login(client)
    assert callback.status_code == 400 and "Search Console" in callback.text


def test_removed_from_invite_list_loses_access(client_for):
    client = client_for()
    _, _, _, issued = tokens(client)
    later = client_for(config(SEO_PULSE_ALLOWED_EMAILS="someone-else@example.com"))
    response, _ = rpc(later, "initialize", token=issued["access_token"])
    assert response.status_code == 401


def test_untrusted_redirect_hosts_cannot_register(client_for):
    client = client_for()
    assert register(client, "https://attacker.example/callback").status_code == 400
    assert register(client, "http://127.0.0.1:6274/oauth/callback").status_code == 201


def test_tampered_or_foreign_tokens_are_rejected(client_for):
    client = client_for()
    _, _, _, issued = tokens(client)
    response, _ = rpc(client, "initialize", token=issued["access_token"][:-4] + "AAAA")
    assert response.status_code == 401
    other = client_for(config(SEO_PULSE_TOKEN_KEYS=Fernet.generate_key().decode()))
    response, _ = rpc(other, "initialize", token=issued["access_token"])
    assert response.status_code == 401


def test_key_rotation_keeps_old_tokens_valid(client_for):
    client = client_for()
    _, _, _, issued = tokens(client)
    rotated = client_for(config(SEO_PULSE_TOKEN_KEYS=f"{Fernet.generate_key().decode()},{KEY}"))
    response, _ = rpc(rotated, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                              "clientInfo": {"name": "t", "version": "1"}},
                      token=issued["access_token"])
    assert response.status_code == 200


def test_codec_expiry_and_kind():
    codec = TokenCodec([KEY])
    old = codec.seal("code", {"x": 1}, now=time.time() - CODE_TTL - 5)
    assert codec.unseal("code", old, CODE_TTL) is None
    fresh = codec.seal("code", {"x": 1})
    assert codec.unseal("code", fresh, CODE_TTL)["x"] == 1
    assert codec.unseal("at", fresh, CODE_TTL) is None


def test_config_refuses_open_signup_by_accident():
    with pytest.raises(ValueError, match="SEO_PULSE_ALLOWED_EMAILS"):
        config(SEO_PULSE_ALLOWED_EMAILS="")
    assert config(SEO_PULSE_ALLOWED_EMAILS="", SEO_PULSE_OPEN_SIGNUP="1").access_policy.allows("x@y.z")
    with pytest.raises(ValueError, match="https"):
        config(SEO_PULSE_PUBLIC_URL="http://pulse.example.test")
