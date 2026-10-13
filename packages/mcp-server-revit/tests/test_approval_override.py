"""The panel's temporary 'auto' window: signed, expiring, and unable to relax look_only."""
from __future__ import annotations

import http.client
import json
import threading

import pytest

from revit_mcp_server import panel_server
from revit_mcp_server.panel_server import build_server
from revit_mcp_server.security import approval_override as ov
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.panel_token import load_or_create_token
from revit_mcp_server.security.workspace import WorkspaceMonitor

TOKEN = "A" * 43


@pytest.fixture(autouse=True)
def _token_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_PANEL_TOKEN_FILE", str(tmp_path / "panel-hub.token"))


def _gate(tmp_path, mode="ask_first", token=TOKEN):
    gate = ApprovalGate(tmp_path / "ws", mode)
    gate.override_token = token
    return gate


def test_no_record_means_baseline(tmp_path):
    assert _gate(tmp_path).approval_mode == "ask_first"


def test_signed_window_turns_auto_on_then_expires(tmp_path):
    gate = _gate(tmp_path)
    ov.enable_auto(gate.workspace_dir, 10, token=TOKEN, now=1000)
    assert ov.active_override(gate.workspace_dir, token=TOKEN, now=1000 + 599) is not None
    assert ov.active_override(gate.workspace_dir, token=TOKEN, now=1000 + 601) is None


def test_gate_follows_the_window_live(tmp_path):
    gate = _gate(tmp_path)
    ov.enable_auto(gate.workspace_dir, 10, token=TOKEN)
    assert gate.approval_mode == "auto"
    assert gate.baseline_approval_mode == "ask_first"
    ov.disable_auto(gate.workspace_dir)
    assert gate.approval_mode == "ask_first"


def test_record_signed_with_another_key_is_ignored(tmp_path):
    gate = _gate(tmp_path)
    ov.enable_auto(gate.workspace_dir, 10, token="B" * 43)  # what an agent writing the file would have to guess
    assert gate.approval_mode == "ask_first"


def test_hand_edited_expiry_is_ignored(tmp_path):
    gate = _gate(tmp_path)
    ov.enable_auto(gate.workspace_dir, 1, token=TOKEN)
    path = ov.override_path(gate.workspace_dir)
    record = json.loads(path.read_text())
    record["expires_at"] += 3600
    path.write_text(json.dumps(record))
    assert gate.approval_mode == "ask_first"


@pytest.mark.parametrize("junk", ["", "not json", "[]", '{"mode": "auto"}', '{"mode":"look_only","set_at":1,"expires_at":9,"sig":"x"}'])
def test_malformed_record_is_ignored(tmp_path, junk):
    gate = _gate(tmp_path)
    ov.override_path(gate.workspace_dir).write_text(junk)
    assert gate.approval_mode == "ask_first"


def test_look_only_is_never_relaxed(tmp_path):
    gate = _gate(tmp_path, mode="look_only")
    ov.enable_auto(gate.workspace_dir, 10, token=TOKEN)
    assert gate.approval_mode == "look_only"


def test_window_is_clamped(tmp_path):
    assert ov.clamp_minutes(0) == ov.MIN_AUTO_MINUTES
    assert ov.clamp_minutes(10_000) == ov.MAX_AUTO_MINUTES
    assert ov.clamp_minutes("junk") == ov.DEFAULT_AUTO_MINUTES


def test_auto_window_lets_an_unplanned_call_through(tmp_path):
    gate = _gate(tmp_path)
    with pytest.raises(Exception):
        gate.check_tool_execution("revit_set_parameter", {})
    ov.enable_auto(gate.workspace_dir, 10, token=TOKEN)
    gate.check_tool_execution("revit_set_parameter", {})
    ov.disable_auto(gate.workspace_dir)
    with pytest.raises(Exception):
        gate.check_tool_execution("revit_set_parameter", {})


# ---- hub route ----

@pytest.fixture
def hub(tmp_path):
    server = build_server(port=0, workspace=WorkspaceMonitor([tmp_path / "ws"]))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], load_or_create_token(), tmp_path / "ws"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _call(port, method, path, token, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                     headers={"Content-Type": "application/json", "X-AMB-Token": token})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read() or b"{}")
    finally:
        conn.close()


def test_hub_route_requires_confirmation(hub):
    port, token, _ = hub
    status, body = _call(port, "POST", "/approval-mode", token, {"mode": "auto"})
    assert status == 400 and body["ok"] is False
    assert _call(port, "GET", "/diagnostics", token)[1]["approval_mode"] == "ask_first"


def test_hub_route_needs_the_token(hub):
    port, _, _ = hub
    status, _ = _call(port, "POST", "/approval-mode", "wrong" * 9, {"mode": "auto", "confirm": True})
    assert status in (401, 429)


def test_hub_route_switches_on_reports_expiry_and_switches_off(hub):
    port, token, ws = hub
    status, body = _call(port, "POST", "/approval-mode", token, {"mode": "auto", "minutes": 5, "confirm": True})
    assert status == 200 and body["approval_mode"] == "auto" and body["auto_expires_at"]
    # A separate gate (what the agent's MCP server process holds) follows the same file.
    other = ApprovalGate(ws, "ask_first")
    assert other.approval_mode == "auto"
    status, body = _call(port, "GET", "/diagnostics", token)
    assert body["approval_mode"] == "auto" and body["auto_expires_at"]
    status, body = _call(port, "POST", "/approval-mode", token, {"mode": "ask_first"})
    assert status == 200 and body["approval_mode"] == "ask_first" and body["auto_expires_at"] is None
    assert other.approval_mode == "ask_first"


def test_hub_route_rejects_unknown_modes(hub):
    port, token, _ = hub
    assert _call(port, "POST", "/approval-mode", token, {"mode": "yolo", "confirm": True})[0] == 400
