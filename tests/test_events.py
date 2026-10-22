"""Hosted tool calls and sign-ins leave one structured log line each (monitoring.md §7):
Cloud Logging turns JSON lines on stderr into jsonPayload, so log-based metrics can
count tools, failures, limit hits and cache hits without logging arguments or emails."""
import json
from unittest.mock import Mock

import pytest

from seo_pulse_mcp import events, server
from seo_pulse_mcp.caller import Caller, acting_for
from seo_pulse_mcp.runtime import ToolRuntime

pytestmark = pytest.mark.anyio
ALICE = Caller("google-sub-alice", "rt", "alice@example.com")


@pytest.fixture
def logged(monkeypatch):
    lines = []
    monkeypatch.setattr(events, "write", lines.append)
    return lambda: [json.loads(line) for line in lines]


def _connectors(monkeypatch, list_sites):
    monkeypatch.setattr(server, "get_connectors", lambda *a, **k: (Mock(list_sites=list_sites), Mock()))


async def test_successful_call_is_logged_without_identity(monkeypatch, logged):
    monkeypatch.setattr(server, "RUNTIME", ToolRuntime())
    _connectors(monkeypatch, lambda: [])
    with acting_for(ALICE):
        await server.mcp.call_tool("list_sites", {})
    [record] = logged()
    assert record["event"] == "tool_call" and record["tool"] == "list_sites"
    assert record["outcome"] == "ok" and record["severity"] == "INFO"
    assert record["subject"] == events.subject_hash("google-sub-alice") and len(record["subject"]) == 12
    assert record["day_total"] == 1 and record["duration_ms"] >= 0
    text = json.dumps(record)
    assert "alice" not in text and "google-sub-alice" not in text and "rt" != record.get("subject")


async def test_errors_limits_and_cache_hits_are_distinguished(monkeypatch, logged):
    monkeypatch.setattr(server, "RUNTIME", ToolRuntime(per_minute=2, cache_seconds=60))
    calls = iter([RuntimeError("Google 授權已失效"), [{"siteUrl": "x"}]])

    def list_sites():
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    _connectors(monkeypatch, list_sites)
    with acting_for(ALICE):
        with pytest.raises(Exception):
            await server.mcp.call_tool("list_sites", {})
        await server.mcp.call_tool("list_sites", {})
        await server.mcp.call_tool("list_sites", {})
        with pytest.raises(Exception):
            await server.mcp.call_tool("gsc_query", {"start_date": "2026-01-01", "end_date": "2026-01-02",
                                                     "dimensions": ["query"], "site_url": "sc-domain:example.com"})
    records = logged()
    assert [r["outcome"] for r in records] == ["error", "ok", "cached", "limited"]
    assert records[0]["error_type"] == "RuntimeError" and records[0]["severity"] == "ERROR"
    assert records[3]["limit"] == "per_minute" and records[3]["severity"] == "WARNING"


async def test_bad_input_is_a_warning(monkeypatch, logged):
    monkeypatch.setattr(server, "RUNTIME", ToolRuntime())
    with acting_for(ALICE):
        with pytest.raises(Exception):
            await server.mcp.call_tool("gsc_query", {"start_date": "2026-01-01", "end_date": "2026-01-02",
                                                     "dimensions": ["query"], "site_url": "example.com"})
    [record] = logged()
    assert record["outcome"] == "error" and record["error_type"] == "ValueError" and record["severity"] == "WARNING"


async def test_local_calls_stay_silent(monkeypatch, logged):
    monkeypatch.setattr(server, "RUNTIME", ToolRuntime())
    _connectors(monkeypatch, lambda: [])
    await server.mcp.call_tool("list_sites", {})
    assert logged() == []


def test_sign_in_outcomes_are_logged(logged, tmp_path):
    from test_hosted_auth import TestClient, build_app, config, google_transport, login
    from shared_state_fixture import sqlite_store

    def run(transport):
        with TestClient(build_app(config(), http_transport=transport, state_store=sqlite_store(tmp_path / "state.db")),
                        base_url="http://testserver",
                        follow_redirects=False) as client:
            login(client)

    run(google_transport())
    run(google_transport(email="stranger@example.com"))
    run(google_transport(scope="openid email"))
    sign_ins = [r for r in logged() if r["event"] == "sign_in"]
    assert [r["outcome"] for r in sign_ins] == ["signed_in", "not_invited", "missing_scope"]
    assert all("@" not in json.dumps(r) for r in sign_ins)
    assert sign_ins[0]["subject"] == events.subject_hash("google-sub-1")
