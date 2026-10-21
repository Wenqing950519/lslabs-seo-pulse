"""Audit 2026-10-21 §3.A: tool calls leave the event loop, run for one caller at a
time, and stay inside per-caller and per-process cost limits."""
import threading
import time
from unittest.mock import Mock

import anyio
import pytest

from seo_pulse_mcp import server
from seo_pulse_mcp.caller import Caller, acting_for, current_caller
from seo_pulse_mcp.connectors.credentials import RemoteUserCredentialProvider
from seo_pulse_mcp.runtime import ToolRuntime

pytestmark = pytest.mark.anyio


@pytest.fixture
def runtime(monkeypatch):
    rt = ToolRuntime()
    monkeypatch.setattr(server, "RUNTIME", rt)
    return rt


async def test_tools_run_in_worker_threads_concurrently(monkeypatch, runtime):
    seen = []

    def slow_sites():
        seen.append(threading.current_thread() is threading.main_thread())
        time.sleep(0.3)
        return []

    monkeypatch.setattr(server, "get_connectors", lambda *a, **k: (Mock(list_sites=slow_sites), Mock()))
    started = time.monotonic()
    async with anyio.create_task_group() as tg:
        for _ in range(3):
            tg.start_soon(server.mcp.call_tool, "list_sites", {})
    assert time.monotonic() - started < 0.8
    assert seen == [False, False, False]


async def test_caller_reaches_the_tool_thread(monkeypatch, runtime):
    caller = Caller(subject="google-sub-1", google_refresh_token="rt-1", email="a@example.com")
    seen = []
    monkeypatch.setattr(server, "get_connectors",
                        lambda *a, **k: (Mock(list_sites=lambda: seen.append(current_caller()) or []), Mock()))
    with acting_for(caller):
        await server.mcp.call_tool("list_sites", {})
    assert seen == [caller]


async def test_per_caller_rate_limit(monkeypatch):
    rt = ToolRuntime(per_minute=2)
    monkeypatch.setattr(server, "RUNTIME", rt)
    monkeypatch.setattr(server, "get_connectors", lambda *a, **k: (Mock(list_sites=lambda: []), Mock()))
    with acting_for(Caller("sub-a", "rt", "a@example.com")):
        await server.mcp.call_tool("list_sites", {})
        await server.mcp.call_tool("list_sites", {})
        with pytest.raises(Exception, match="每分鐘"):
            await server.mcp.call_tool("list_sites", {})
    with acting_for(Caller("sub-b", "rt", "b@example.com")):
        await server.mcp.call_tool("list_sites", {})


async def test_process_daily_cap(monkeypatch):
    rt = ToolRuntime(daily_total=1)
    monkeypatch.setattr(server, "RUNTIME", rt)
    monkeypatch.setattr(server, "get_connectors", lambda *a, **k: (Mock(list_sites=lambda: []), Mock()))
    with acting_for(Caller("sub-a", "rt", "a@example.com")):
        await server.mcp.call_tool("list_sites", {})
        with pytest.raises(Exception, match="今日"):
            await server.mcp.call_tool("list_sites", {})


async def test_identical_calls_are_cached_per_caller(monkeypatch):
    rt = ToolRuntime(cache_seconds=60)
    monkeypatch.setattr(server, "RUNTIME", rt)
    calls = []
    monkeypatch.setattr(server, "get_connectors",
                        lambda *a, **k: (Mock(list_sites=lambda: calls.append(1) or [{"siteUrl": "x"}]), Mock()))
    with acting_for(Caller("sub-a", "rt", "a@example.com")):
        await server.mcp.call_tool("list_sites", {})
        await server.mcp.call_tool("list_sites", {})
    with acting_for(Caller("sub-b", "rt", "b@example.com")):
        await server.mcp.call_tool("list_sites", {})
    assert len(calls) == 2


def test_hosted_calls_require_explicit_site_and_property(monkeypatch):
    monkeypatch.setenv("SEO_PULSE_CONNECTOR", "google")
    with acting_for(Caller("sub-a", "rt", "a@example.com")):
        with pytest.raises(ValueError, match="list_sites"):
            server.gsc_query("2026-01-01", "2026-01-02", ["query"])
        with pytest.raises(ValueError, match="list_ga4_properties"):
            server.ga4_report("2026-01-01", "2026-01-02", site_url="sc-domain:example.com")
        with pytest.raises(ValueError, match="site_url"):
            server.weekly_report(property_id="123")


def test_ga4_tools_derive_hosts_from_site_url(monkeypatch):
    calls = []

    def fake(settings=None, **kwargs):
        calls.append(kwargs)
        return Mock(), Mock(report=Mock(return_value=[]))

    monkeypatch.setattr(server, "get_connectors", fake)
    server.ga4_report("2026-01-01", "2026-01-02", property_id="123", site_url="sc-domain:example.org")
    assert calls[-1]["production_hosts"] == ("example.org", "www.example.org")


def test_list_ga4_properties_fixture():
    props = server.list_ga4_properties()
    assert props and props[0]["fake"] and props[0]["property_id"].isdigit()


# --- per-caller Google credentials --------------------------------------------

class _FakeCredentials:
    refreshes = 0

    def __init__(self, token=None, refresh_token=None, **kwargs):
        self.token, self.refresh_token, self.expiry_ok = token, refresh_token, False

    @property
    def valid(self):
        return self.expiry_ok

    def refresh(self, request):
        time.sleep(0.05)
        type(self).refreshes += 1
        self.token, self.expiry_ok = f"at-{self.refresh_token}", True


def test_remote_provider_refreshes_once_per_caller_under_concurrency():
    _FakeCredentials.refreshes = 0
    provider = RemoteUserCredentialProvider("cid", "secret", credentials_factory=_FakeCredentials)
    caller = Caller("sub-a", "rt-a", "a@example.com")
    results = []
    threads = [threading.Thread(target=lambda: results.append(provider.get("gsc", caller))) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert _FakeCredentials.refreshes == 1
    assert len({id(r) for r in results}) == 1
    other = provider.get("ga4", Caller("sub-b", "rt-b", "b@example.com"))
    assert other.token == "at-rt-b" and _FakeCredentials.refreshes == 2


def test_remote_provider_requires_a_caller_and_reports_revocation():
    from google.auth.exceptions import RefreshError

    class Revoked(_FakeCredentials):
        def refresh(self, request):
            raise RefreshError("invalid_grant")

    provider = RemoteUserCredentialProvider("cid", "secret", credentials_factory=Revoked)
    with pytest.raises(RuntimeError, match="重新連線"):
        provider.get("gsc", Caller("sub-a", "rt-a", "a@example.com"))
    with pytest.raises(RuntimeError):
        provider.get("gsc", None)


def test_local_provider_caches_valid_credentials(monkeypatch):
    from seo_pulse_mcp.connectors import credentials as c
    loads = []
    fake = Mock(valid=True)
    monkeypatch.setattr(c, "_credentials", lambda service, **k: loads.append(service) or fake)
    provider = c.LocalFileCredentialProvider()
    assert provider.get("gsc") is provider.get("gsc") is fake
    assert loads == ["gsc"]
