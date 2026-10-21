"""A2/A6/A7: HTTP transport CLI/env resolution, the non-loopback safety gate, and
server instructions — without actually starting a long-running server.
"""
from types import SimpleNamespace as NS

import pytest

from seo_pulse_mcp import server


def _args(transport=None, host=None, port=None, allow_unauthenticated_remote=False):
    return NS(transport=transport, host=host, port=port,
              allow_unauthenticated_remote=allow_unauthenticated_remote)


# --- A2: CLI and env both start http mode; CLI wins when both set ---------------

def test_no_args_no_env_defaults_to_stdio():
    assert server.resolve_runtime_config(_args(), env={}) == ("stdio", "127.0.0.1", 8000, False)


def test_env_var_selects_http_mode():
    env = {"SEO_PULSE_TRANSPORT": "http", "SEO_PULSE_HTTP_HOST": "127.0.0.1", "SEO_PULSE_HTTP_PORT": "9100"}
    assert server.resolve_runtime_config(_args(), env=env) == ("http", "127.0.0.1", 9100, False)


def test_cli_flag_selects_http_mode():
    args = _args(transport="http", host="127.0.0.1", port=9200)
    assert server.resolve_runtime_config(args, env={}) == ("http", "127.0.0.1", 9200, False)


def test_cli_overrides_conflicting_env():
    env = {"SEO_PULSE_TRANSPORT": "stdio", "SEO_PULSE_HTTP_HOST": "0.0.0.0", "SEO_PULSE_HTTP_PORT": "9000"}
    args = _args(transport="http", host="127.0.0.1", port=9300)
    assert server.resolve_runtime_config(args, env=env) == ("http", "127.0.0.1", 9300, False)


def test_cli_parses_serve_transport_http():
    """`seo-pulse serve --transport http --host 127.0.0.1 --port 9100`"""
    args = server._build_parser().parse_args(
        ["serve", "--transport", "http", "--host", "127.0.0.1", "--port", "9100"])
    assert args.command == "serve"
    assert server.resolve_runtime_config(args, env={}) == ("http", "127.0.0.1", 9100, False)


def test_cli_parses_bare_transport_http_without_serve_word():
    """`python -m seo_pulse_mcp.server --transport http` (no leading "serve")."""
    args = server._build_parser().parse_args(["--transport", "http"])
    assert args.command is None
    assert server.resolve_runtime_config(args, env={})[0] == "http"


def test_bare_invocation_without_args_still_stdio():
    args = server._build_parser().parse_args([])
    assert server.resolve_runtime_config(args, env={}) == ("stdio", "127.0.0.1", 8000, False)


# --- A6: safety gate for non-loopback binding ------------------------------------

def test_serve_rejects_non_loopback_without_flag(monkeypatch, capsys):
    monkeypatch.setattr(server.mcp, "run", lambda **kw: pytest.fail("must not start the server"))
    with pytest.raises(SystemExit) as excinfo:
        server.serve("http", host="0.0.0.0", port=9000, allow_unauthenticated_remote=False)
    assert excinfo.value.code != 0
    assert "--allow-unauthenticated-remote" in capsys.readouterr().err


def test_serve_warns_and_runs_with_flag(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda **kw: calls.append(kw))
    server.serve("http", host="0.0.0.0", port=9000, allow_unauthenticated_remote=True)
    assert calls == [{"transport": "streamable-http"}]
    err = capsys.readouterr().err
    assert "警告" in err and "0.0.0.0" in err


def test_serve_loopback_no_warning_no_rejection(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda **kw: calls.append(kw))
    server.serve("http", host="127.0.0.1", port=8000, allow_unauthenticated_remote=False)
    assert calls == [{"transport": "streamable-http"}]
    assert capsys.readouterr().err == ""


def test_cli_rejects_0_0_0_0_without_flag_end_to_end(monkeypatch, capsys):
    monkeypatch.setattr(server.mcp, "run", lambda **kw: pytest.fail("must not start the server"))
    with pytest.raises(SystemExit):
        server.main(["serve", "--transport", "http", "--host", "0.0.0.0"])
    assert "--allow-unauthenticated-remote" in capsys.readouterr().err


def test_cli_allows_0_0_0_0_with_flag_end_to_end(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda **kw: calls.append(kw))
    server.main(["serve", "--transport", "http", "--host", "0.0.0.0", "--allow-unauthenticated-remote"])
    assert calls == [{"transport": "streamable-http"}]
    assert "警告" in capsys.readouterr().err


def test_env_var_alone_does_not_allow_remote(monkeypatch, capsys):
    """SEO_PULSE_ALLOW_UNAUTHENTICATED_REMOTE=1 alone (no CLI flag) must NOT bypass
    the non-loopback safety gate; only --allow-unauthenticated-remote may."""
    monkeypatch.setattr(server.mcp, "run", lambda **kw: pytest.fail("must not start the server"))
    monkeypatch.setenv("SEO_PULSE_ALLOW_UNAUTHENTICATED_REMOTE", "1")
    with pytest.raises(SystemExit) as excinfo:
        server.main(["serve", "--transport", "http", "--host", "0.0.0.0"])
    assert excinfo.value.code != 0
    assert "--allow-unauthenticated-remote" in capsys.readouterr().err


# --- A7: server instructions ------------------------------------------------------

def test_instructions_first_512_chars_contain_required_phrases():
    head = server.INSTRUCTIONS[:512]
    assert "先 list_sites 驗證" in head
    assert '用 weekly_report(format="markdown")、只換兩段佔位、數字不改' in head


def test_instructions_total_length_within_budget():
    assert len(server.INSTRUCTIONS) <= 2000


def test_mcp_instructions_match_module_constant():
    assert server.mcp.instructions == server.INSTRUCTIONS
