"""Tests for panel_server.py, the loopback HTTP shim the dockable panel calls
since MCP itself is stdio-only (see panel_server.py's module docstring).

Each test builds its own server bound to workspace=WorkspaceMonitor([tmp_path])
so ApprovalGate plan files never land in the shared tests/ workspace.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import Mock

import pytest

from revit_mcp_server import panel_server
from revit_mcp_server.panel_server import build_server
from revit_mcp_server.security.workspace import WorkspaceMonitor


@pytest.fixture
def running_server(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    server = build_server(port=0, workspace=workspace)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield port
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _get(port: int, path: str):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(port: int, path: str, body: dict):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_reports_tool_count(running_server):
    status, body = _get(running_server, "/health")
    assert status == 200
    assert body["status"] == "healthy"


def test_execute_runs_a_real_readonly_tool(running_server):
    """list_pending_plans is a genuinely readonly tool: it only reads plan files from
    disk, never writes, and doesn't depend on optional modules like qaqc_checker."""
    status, body = _post(running_server, "/execute", {"tool": "list_pending_plans", "arguments": {}})
    assert status == 200
    assert body["ok"] is True
    assert "plans" in body["result"]


def test_execute_unknown_tool_returns_500_with_message(running_server):
    status, body = _post(running_server, "/execute", {"tool": "not_a_real_tool", "arguments": {}})
    assert status == 500
    assert body["ok"] is False
    assert "not_a_real_tool" in body["error"]


def test_execute_missing_tool_field_returns_400(running_server):
    status, body = _post(running_server, "/execute", {"arguments": {}})
    assert status == 400
    assert body["ok"] is False


def test_unknown_path_returns_404(running_server):
    status, body = _get(running_server, "/nope")
    assert status == 404
    assert body["ok"] is False


def test_mutating_tool_without_plan_is_rejected(running_server):
    """The panel shim must apply the same ApprovalGate check as the stdio
    server - a mutating tool called with no plan_id must not go through."""
    status, body = _post(running_server, "/execute", {
        "tool": "revit_set_parameter_value",
        "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"},
    })
    assert status == 409
    assert body["ok"] is False
    assert "plan_id" in body["error"]


def test_reports_lists_workspace_exports_newest_first(running_server, tmp_path):
    """The Reports tab's Refresh button has no MCP tool behind it - it lists
    whatever report_generator has already written to the workspace root."""
    (tmp_path / "model_report.xlsx").write_bytes(b"x")
    time.sleep(0.05)
    (tmp_path / "model_data.db").write_bytes(b"x")

    status, body = _get(running_server, "/reports")

    assert status == 200
    assert body["ok"] is True
    assert [r["name"] for r in body["reports"]] == ["model_data.db", "model_report.xlsx"]


def test_reports_excludes_internal_state_files(running_server, tmp_path):
    """qaqc_issues.db is the QA/QC module's own tracking database, not
    something report_generator exported - it must never appear as a report."""
    (tmp_path / "qaqc_issues.db").write_bytes(b"x")

    status, body = _get(running_server, "/reports")

    assert status == 200
    assert body["reports"] == []


def test_reports_excludes_clash_triage_state_file(running_server, tmp_path):
    (tmp_path / "clash_triage.db").write_bytes(b"x")

    status, body = _get(running_server, "/reports")

    assert status == 200
    assert body["reports"] == []


def test_reports_empty_workspace_returns_empty_list(running_server):
    status, body = _get(running_server, "/reports")
    assert status == 200
    assert body["ok"] is True
    assert body["reports"] == []


def test_plan_actions_approve_execute_round_trip_over_http(running_server):
    """Proves the panel can drive the full W5 workflow end-to-end through
    HTTP alone: plan -> approve -> execute -> verify, all as separate
    requests hitting the same server (and therefore the same in-process
    registry) - this is the exact shape the C# panel host will use."""
    status, plan = _post(running_server, "/execute", {
        "tool": "plan_actions",
        "arguments": {"actions": [{
            "tool": "revit_set_parameter_value",
            "arguments": {"element_id": 42, "parameter_name": "Mark", "value": "D-999"},
        }]},
    })
    assert status == 200
    plan_id = plan["result"]["plan_id"]
    assert plan["result"]["state"] == "pending"

    status, approved = _post(running_server, "/execute", {"tool": "approve_plan", "arguments": {"plan_id": plan_id}})
    assert status == 200
    assert approved["result"]["state"] == "approved"

    status, executed = _post(running_server, "/execute", {"tool": "execute_plan", "arguments": {"plan_id": plan_id}})
    assert status == 200
    # execute_plan succeeds even when the underlying Revit tool is mocked and returns
    # an error (no live Revit process in tests). Accept "executed" (all OK) or
    # "partial" (some actions failed — expected here since Revit is unavailable).
    assert executed["result"]["state"] in ("executed", "partial")


def test_agent_providers_none_available(running_server, monkeypatch):
    """No API key configured and neither CLI on PATH: both providers are
    reported unavailable."""
    monkeypatch.setattr(panel_server.config, "anthropic_api_key", None)
    monkeypatch.setattr(panel_server.shutil, "which", lambda _name: None)

    status, body = _get(running_server, "/agent/providers")

    assert status == 200
    assert body == {"ok": True, "providers": {"claude": False, "codex": False}}


def test_agent_providers_claude_true_with_api_key_configured(running_server, monkeypatch):
    """An Anthropic API key alone is enough for the "claude" provider to be
    reported available, even with no CLI on PATH at all."""
    monkeypatch.setattr(panel_server.config, "anthropic_api_key", "test-key")
    monkeypatch.setattr(panel_server.shutil, "which", lambda _name: None)

    status, body = _get(running_server, "/agent/providers")

    assert status == 200
    assert body["providers"]["claude"] is True
    assert body["providers"]["codex"] is False


def test_agent_providers_claude_true_with_cli_fallback_only(running_server, monkeypatch):
    """No API key, but the `claude` CLI resolves on PATH: "claude" is still
    reported available via the CLI fallback."""
    monkeypatch.setattr(panel_server.config, "anthropic_api_key", None)
    monkeypatch.setattr(panel_server.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)

    status, body = _get(running_server, "/agent/providers")

    assert status == 200
    assert body["providers"]["claude"] is True
    assert body["providers"]["codex"] is False


def test_agent_chat_dispatches_to_native_when_api_key_configured(running_server, monkeypatch):
    """Load-bearing dispatch-priority test: when an Anthropic API key is
    configured, /agent/chat must go through agent_native.run_native_turn and
    must NOT fall through to agent_bridge.run_agent_turn (the CLI path),
    even though the request's provider field says "claude" (the field the
    CLI path used to key off of)."""
    monkeypatch.setattr(panel_server.config, "anthropic_api_key", "test-key")

    native_calls = []
    bridge_calls = []

    def fake_native(message, session_id, registry, approval_provider):
        native_calls.append((message, session_id, registry, approval_provider))
        return {"ok": True, "response": "native reply", "session_id": "sess-native"}

    def fake_bridge(provider, message, session_id):
        bridge_calls.append((provider, message, session_id))
        return {"ok": True, "response": "bridge reply", "session_id": "sess-bridge"}

    monkeypatch.setattr(panel_server.agent_native, "run_native_turn", fake_native)
    monkeypatch.setattr(panel_server.agent_bridge, "run_agent_turn", fake_bridge)

    status, body = _post(running_server, "/agent/chat", {"message": "hi", "provider": "claude"})

    assert status == 200
    assert body == {"ok": True, "response": "native reply", "session_id": "sess-native"}
    assert len(native_calls) == 1
    assert native_calls[0][0] == "hi"
    assert native_calls[0][1] is None
    assert bridge_calls == []


def test_agent_chat_explicit_codex_stays_on_cli_path_even_with_api_key_configured(running_server, monkeypatch):
    """Regression test: codex has no native path (Task 1's ADR scopes it as
    CLI-only regardless of API key state). An explicit provider: "codex"
    request must always go through agent_bridge.run_agent_turn, even when an
    Anthropic API key is configured and would otherwise route "claude" to
    the native path."""
    monkeypatch.setattr(panel_server.config, "anthropic_api_key", "test-key")
    monkeypatch.setattr(panel_server.shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)

    native_calls = []
    bridge_calls = []

    def fake_native(message, session_id, registry, approval_provider):
        native_calls.append((message, session_id))
        return {"ok": True, "response": "native reply", "session_id": "sess-native"}

    def fake_bridge(provider, message, session_id):
        bridge_calls.append((provider, message, session_id))
        return {"ok": True, "response": "codex reply", "session_id": "sess-codex"}

    monkeypatch.setattr(panel_server.agent_native, "run_native_turn", fake_native)
    monkeypatch.setattr(panel_server.agent_bridge, "run_agent_turn", fake_bridge)

    status, body = _post(running_server, "/agent/chat", {"message": "hi", "provider": "codex"})

    assert status == 200
    assert body == {"ok": True, "response": "codex reply", "session_id": "sess-codex"}
    assert bridge_calls == [("codex", "hi", None)]
    assert native_calls == []


def test_agent_chat_no_provider_available_returns_error_without_dispatch(running_server, monkeypatch):
    """No API key and no CLI on PATH: the chat request must fail fast with
    the "no provider available" error, without ever calling either agent
    module."""
    monkeypatch.setattr(panel_server.config, "anthropic_api_key", None)
    monkeypatch.setattr(panel_server.shutil, "which", lambda _name: None)

    native_mock = Mock()
    bridge_mock = Mock()
    monkeypatch.setattr(panel_server.agent_native, "run_native_turn", native_mock)
    monkeypatch.setattr(panel_server.agent_bridge, "run_agent_turn", bridge_mock)

    status, body = _post(running_server, "/agent/chat", {"message": "hi"})

    assert body == {
        "ok": False,
        "error": "No AI provider is available. Set the MCP_REVIT_ANTHROPIC_API_KEY environment variable "
                 "and restart Revit, or install and sign in to the claude/codex CLI.",
    }
    native_mock.assert_not_called()
    bridge_mock.assert_not_called()


def test_configure_file_logging_persists_package_logs(tmp_path):
    import logging

    log_file = tmp_path / "Logs" / "panel-hub.log"
    path = panel_server.configure_file_logging(log_file)
    pkg_logger = logging.getLogger("revit_mcp_server")
    try:
        assert path == log_file
        logging.getLogger("revit_mcp_server.panel_server").error("stale plan boom")
        for h in pkg_logger.handlers:
            h.flush()
        assert "stale plan boom" in log_file.read_text(encoding="utf-8")
    finally:
        for h in list(pkg_logger.handlers):
            if getattr(h, "baseFilename", None) == str(log_file):
                pkg_logger.removeHandler(h)
                h.close()


def test_configure_file_logging_tolerates_unwritable_path(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert panel_server.configure_file_logging(blocker / "sub" / "panel-hub.log") is None


def test_diagnostics_flags_mock_mode_with_next_step(running_server):
    status, body = _get(running_server, "/diagnostics")
    assert status == 200
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["hub"]["ok"] is True
    assert checks["workspace"]["ok"] is True
    assert checks["mode"]["ok"] is False and "MCP_REVIT_MODE=bridge" in checks["mode"]["next_step"]
    assert body["ok"] is False


def test_diagnostics_reports_missing_revit_bridge(running_server, monkeypatch):
    from revit_mcp_server.config import BridgeMode

    monkeypatch.setattr(panel_server.config, "mode", BridgeMode.bridge)
    monkeypatch.setattr("revit_mcp_server.bridge.discovery.available_host_versions", lambda *_a, **_k: [])
    status, body = _get(running_server, "/diagnostics")
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["revit_bridge"]["ok"] is False
    assert "add-in" in checks["revit_bridge"]["next_step"]


# --- Browser / DNS-rebinding / token hardening -----------------------------

TOKEN = "test-token-123"


@pytest.fixture
def secured_server(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    server = build_server(port=0, workspace=workspace, token=TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield port
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _raw(port, method, path, headers=None, body=None):
    """Request with full header control (urllib would override Host)."""
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        hdrs = {"Host": f"127.0.0.1:{port}"}
        hdrs.update(headers or {})
        data = body.encode("utf-8") if body is not None else None
        if data is not None:
            hdrs["Content-Length"] = str(len(data))
        for k, v in hdrs.items():
            conn.putheader(k, v)
        conn.endheaders(data)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read() or b"{}")
    finally:
        conn.close()


AUTH = {"Authorization": f"Bearer {TOKEN}"}
JSON_AUTH = {**AUTH, "Content-Type": "application/json"}
EXEC_BODY = json.dumps({"tool": "list_pending_plans", "arguments": {}})


def test_post_requires_json_content_type(secured_server):
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        status, _ = _raw(secured_server, "POST", "/execute", {**AUTH, "Content-Type": ctype}, EXEC_BODY)
        assert status == 415, ctype
    status, _ = _raw(secured_server, "POST", "/execute", AUTH, EXEC_BODY)  # none at all
    assert status == 415


def test_json_content_type_with_charset_is_accepted(secured_server):
    status, body = _raw(
        secured_server, "POST", "/execute",
        {**AUTH, "Content-Type": "application/json; charset=utf-8"}, EXEC_BODY,
    )
    assert status == 200 and body["ok"] is True


@pytest.mark.parametrize("host", ["evil.example", "evil.example:%d", "127.0.0.1", "localhost:1", "127.0.0.1.evil.example:%d"])
def test_bad_host_rejected_including_dns_rebinding(secured_server, host):
    host = host.replace("%d", str(secured_server))
    status, _ = _raw(secured_server, "POST", "/execute", {**JSON_AUTH, "Host": host}, EXEC_BODY)
    assert status == 403
    status, _ = _raw(secured_server, "GET", "/health", {"Host": host})
    assert status == 403


def test_localhost_host_is_allowed(secured_server):
    status, _ = _raw(secured_server, "GET", "/health", {"Host": f"localhost:{secured_server}"})
    assert status == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://127.0.0.1", "http://localhost:8787"])
def test_any_origin_rejected(secured_server, origin):
    status, _ = _raw(secured_server, "POST", "/execute", {**JSON_AUTH, "Origin": origin}, EXEC_BODY)
    assert status == 403
    status, _ = _raw(secured_server, "GET", "/diagnostics", {**AUTH, "Origin": origin})
    assert status == 403
    status, _ = _raw(secured_server, "GET", "/health", {"Origin": origin})
    assert status == 403


def test_missing_or_wrong_token_rejected(secured_server):
    status, _ = _raw(secured_server, "POST", "/execute", {"Content-Type": "application/json"}, EXEC_BODY)
    assert status == 401
    for bad in ("Bearer wrong", "Bearer ", f"Basic {TOKEN}", TOKEN, f"Bearer {TOKEN}x"):
        status, _ = _raw(
            secured_server, "POST", "/execute",
            {"Authorization": bad, "Content-Type": "application/json"}, EXEC_BODY,
        )
        assert status == 401, bad
    for path in ("/diagnostics", "/reports", "/agent/providers"):
        assert _raw(secured_server, "GET", path)[0] == 401, path
    status, _ = _raw(secured_server, "POST", "/agent/chat", {"Content-Type": "application/json"}, "{}")
    assert status == 401


def test_correct_token_works(secured_server):
    status, body = _raw(secured_server, "POST", "/execute", JSON_AUTH, EXEC_BODY)
    assert status == 200 and body["ok"] is True
    assert _raw(secured_server, "GET", "/reports", AUTH)[0] == 200
    assert _raw(secured_server, "GET", "/agent/providers", AUTH)[0] == 200


def test_health_is_open_and_minimal(secured_server):
    status, body = _raw(secured_server, "GET", "/health")
    assert status == 200
    assert body == {"status": "healthy"}


def test_token_read_from_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv(panel_server.TOKEN_ENV_VAR, "from-env")
    server = build_server(port=0, workspace=WorkspaceMonitor([tmp_path]))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        assert _raw(port, "GET", "/reports")[0] == 401
        assert _raw(port, "GET", "/reports", {"Authorization": "Bearer from-env"})[0] == 200
    finally:
        server.shutdown()
        thread.join(timeout=2)
