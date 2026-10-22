"""Durable admission must survive independent processes and application restarts."""
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
import sqlite3
import time
from unittest.mock import Mock

import pytest
import anyio

from seo_pulse_mcp.admission import AdmissionUnavailable, LimitExceeded, SharedAdmissionStore
from seo_pulse_mcp.caller import Caller
from seo_pulse_mcp.runtime import ToolRuntime
from shared_state_fixture import sqlite_store


NOW = 1_800_000_000.0


def _reserve(arguments):
    filename, subject, cap = arguments
    try:
        return sqlite_store(filename, clock=lambda: NOW).admit(subject, per_minute=30, per_day=30, daily_total=cap)
    except LimitExceeded:
        return None


def _claim(filename):
    return sqlite_store(filename, clock=lambda: NOW).claim_code("private-authorization-code", NOW + 120)


def test_daily_budget_is_atomic_across_processes_and_restart(tmp_path):
    filename = str(tmp_path / "state.db")
    sqlite_store(filename)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(_reserve, [(filename, f"user-{i}", 5) for i in range(12)]))
    assert sorted(value for value in results if value is not None) == [1, 2, 3, 4, 5]
    assert _reserve((filename, "new-user-after-restart", 5)) is None


def test_per_user_limits_and_rolling_minute_survive_new_store_objects(tmp_path):
    filename = tmp_path / "state.db"
    now = [NOW]
    first = sqlite_store(filename, clock=lambda: now[0])
    second = sqlite_store(filename, clock=lambda: now[0])
    limits = dict(per_minute=2, per_day=3, daily_total=10)
    first.admit("alice", **limits)
    second.admit("alice", **limits)
    with pytest.raises(LimitExceeded) as denied:
        first.admit("alice", **limits)
    assert denied.value.limit == "per_minute"
    assert second.admit("bob", **limits) == 3
    now[0] += 60
    assert second.admit("alice", **limits) == 4
    with pytest.raises(LimitExceeded) as denied:
        first.admit("alice", **limits)
    assert denied.value.limit == "per_day"
    now[0] += 86400
    assert first.admit("alice", **limits) == 1


def test_authorization_code_claim_is_atomic_and_survives_restart(tmp_path):
    filename = str(tmp_path / "state.db")
    sqlite_store(filename)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(_claim, [filename] * 10))
    assert results.count(True) == 1
    assert _claim(filename) is False
    with sqlite3.connect(filename) as connection:
        rows = connection.execute("SELECT id, body FROM documents").fetchall()
    assert "private-authorization-code" not in json.dumps(rows)
    assert "expire_at" in json.loads(rows[0][1])
    assert sqlite_store(filename, clock=lambda: NOW + 121).claim_code("never-used-but-expired", NOW + 120) is False


def test_window_storage_is_bounded_and_does_not_store_raw_identity(tmp_path):
    filename = tmp_path / "state.db"
    for day in range(10):
        store = sqlite_store(filename, clock=lambda: NOW + day * 86400)
        store.admit("private-google-subject", per_minute=2, per_day=3, daily_total=4)
    with sqlite3.connect(filename) as connection:
        rows = connection.execute("SELECT id, body FROM documents").fetchall()
    assert len(rows) == 2, "one global and one caller document, overwritten across windows"
    assert "private-google-subject" not in json.dumps(rows)
    assert all("expire_at" in json.loads(row[1]) for row in rows)


def test_backend_errors_fail_closed_without_exposing_internal_errors():
    store = SharedAdmissionStore(Mock(run=Mock(side_effect=OSError("private backend details"))),
                                 namespace="test", hmac_key="test-key-" * 8)
    with pytest.raises(AdmissionUnavailable, match="暫時") as error:
        store.admit("user", per_minute=2, per_day=3, daily_total=4)
    assert "private backend details" not in str(error.value)
    with pytest.raises(AdmissionUnavailable):
        store.claim_code("code", NOW + 120)


@pytest.mark.anyio
async def test_hosted_runtime_cannot_call_google_when_shared_state_is_unavailable():
    function = Mock(return_value="should not run")
    caller = Caller("subject", "private-google-refresh-token", "private@example.test")
    broken = Mock(admit=Mock(side_effect=AdmissionUnavailable()), check_available=Mock(side_effect=AdmissionUnavailable()))
    runtime = ToolRuntime(shared_store=broken, require_shared=True, per_minute=2, per_day=3, daily_total=4)
    with pytest.raises(AdmissionUnavailable):
        await runtime.run("fixture", function, {}, caller)
    function.assert_not_called()
    missing = ToolRuntime(require_shared=True)
    with pytest.raises(AdmissionUnavailable):
        await missing.run("fixture", function, {}, caller)
    function.assert_not_called()
    assert await missing.run("fixture", lambda: "local", {}, None) == "local"


@pytest.mark.anyio
async def test_hosted_cache_hit_does_not_bypass_a_shared_state_outage(tmp_path):
    store = sqlite_store(tmp_path / "state.db")
    runtime = ToolRuntime(shared_store=store, require_shared=True, cache_seconds=60,
                          per_minute=2, per_day=3, daily_total=4)
    caller = Caller("subject", "rt", "a@example.test")
    function = Mock(return_value="cached data")
    assert await runtime.run("fixture", function, {}, caller) == "cached data"
    store.backend = Mock(run=Mock(side_effect=OSError("offline")))
    with pytest.raises(AdmissionUnavailable):
        await runtime.run("fixture", function, {}, caller)
    assert function.call_count == 1


@pytest.mark.anyio
async def test_timed_out_admission_never_runs_google_after_late_commit(monkeypatch):
    from seo_pulse_mcp import admission
    monkeypatch.setattr(admission, "STATE_TIMEOUT_SECONDS", 0.02)
    committed = []

    def slow_admit(*args, **kwargs):
        time.sleep(0.1)
        committed.append(True)
        return 1

    runtime = ToolRuntime(shared_store=Mock(admit=slow_admit), require_shared=True,
                          per_minute=2, per_day=3, daily_total=4)
    function = Mock()
    with pytest.raises(AdmissionUnavailable):
        await runtime.run("fixture", function, {}, Caller("subject", "rt", "a@example.test"))
    await anyio.sleep(0.15)
    assert committed == [True]
    function.assert_not_called()
