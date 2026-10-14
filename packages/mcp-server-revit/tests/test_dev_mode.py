"""Person-operated Dev mode without weakening existing transport or plan checks."""
from __future__ import annotations

import asyncio
import http.client
import json
import os
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from helpers import human_approve
from revit_mcp_server.panel_server import build_server
from revit_mcp_server.providers.revit_context import get_context
from revit_mcp_server.registry_factory import build_registry
from revit_mcp_server.security import approval_override as auto
from revit_mcp_server.security import approval as approval_module
from revit_mcp_server.security import dev_mode as dev
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import gate_before, run_gated_tool
from revit_mcp_server.security.panel_token import load_or_create_token
from revit_mcp_server.security.read_mode import ReadModeViolation
from revit_mcp_server.security.workspace import WorkspaceMonitor

TOKEN = "A" * 43
SET = "revit_set_parameter_value"


def _gate(tmp_path, mode="ask_first"):
    gate = ApprovalGate(tmp_path / "ws", mode)
    gate.override_token = TOKEN
    return gate


def test_dev_survives_restart_and_has_no_expiry(tmp_path):
    gate = _gate(tmp_path)
    dev.enable_dev(gate.workspace_dir, token=TOKEN, now=1)
    restarted = _gate(tmp_path)
    assert restarted.dev_mode and restarted.approval_mode == "auto"
    state = restarted.approval_state()
    assert state["configured_mode"] == "ask_first"
    assert state["dev_mode"] is True
    assert state["auto_window"] is None and state["auto_expires_at"] is None
    dev.disable_dev(gate.workspace_dir)
    assert restarted.approval_mode == "ask_first" and not restarted.dev_mode


def test_new_process_reads_same_signed_state(tmp_path):
    ws = tmp_path / "ws"
    token = load_or_create_token()
    dev.enable_dev(ws, token=token)
    script = "from pathlib import Path; from revit_mcp_server.security.approval import ApprovalGate; import sys; g=ApprovalGate(Path(sys.argv[1]), 'ask_first'); print(g.dev_mode, g.approval_mode)"
    result = subprocess.run([sys.executable, "-c", script, str(ws)], capture_output=True, text=True,
                            timeout=15, check=True, env=os.environ.copy())
    assert result.stdout.strip() == "True auto"


@pytest.mark.parametrize("junk", ["", "[]", "{}", 'not json', '{"mode":"dev","set_at":true,"sig":"x"}'])
def test_malformed_record_fails_closed(tmp_path, junk):
    gate = _gate(tmp_path)
    dev.dev_path(gate.workspace_dir).write_text(junk)
    assert not gate.dev_mode and gate.approval_mode == "ask_first"


def test_signature_token_rotation_tampering_and_workspace_copy(tmp_path):
    gate = _gate(tmp_path)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    assert not dev.active_dev(gate.workspace_dir, token="B" * 43)
    other = tmp_path / "other"
    other.mkdir()
    other.joinpath(dev.DEV_FILENAME).write_bytes(dev.dev_path(gate.workspace_dir).read_bytes())
    assert not dev.active_dev(other, token=TOKEN)
    record = json.loads(dev.dev_path(gate.workspace_dir).read_text())
    record["set_at"] += 1
    dev.dev_path(gate.workspace_dir).write_text(json.dumps(record))
    assert not gate.dev_mode


def test_old_signed_record_stays_revoked_after_off_and_reenable(tmp_path):
    gate = _gate(tmp_path)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    old = dev.dev_path(gate.workspace_dir).read_bytes()
    dev.disable_dev(gate.workspace_dir)
    dev.dev_path(gate.workspace_dir).write_bytes(old)
    assert not gate.dev_mode
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    current = dev.dev_path(gate.workspace_dir).read_bytes()
    assert current != old and gate.dev_mode
    dev.dev_path(gate.workspace_dir).write_bytes(old)
    assert not gate.dev_mode
    dev.dev_path(gate.workspace_dir).write_bytes(current)
    assert gate.dev_mode


def test_workspace_revocation_is_independent_and_authority_required(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    dev.enable_dev(a, token=TOKEN)
    dev.enable_dev(b, token=TOKEN)
    dev.disable_dev(a)
    assert not dev.active_dev(a, token=TOKEN) and dev.active_dev(b, token=TOKEN)
    dev._authority_path(b).unlink()
    assert not dev.active_dev(b, token=TOKEN)


def test_off_revokes_even_when_workspace_record_cannot_be_removed(tmp_path, monkeypatch):
    gate = _gate(tmp_path)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    record_path = dev.dev_path(gate.workspace_dir)
    real_unlink = type(record_path).unlink
    def unlink(path, *args, **kwargs):
        if path == record_path:
            raise PermissionError("record locked")
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(type(record_path), "unlink", unlink)
    with pytest.raises(PermissionError):
        dev.disable_dev(gate.workspace_dir)
    assert record_path.exists() and not gate.dev_mode


def test_concurrent_process_switches_cannot_restore_revoked_records(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    load_or_create_token()
    script = """from pathlib import Path
import sys
from revit_mcp_server.security.dev_mode import set_panel_mode, dev_path
from revit_mcp_server.security.panel_token import read_token
ws, key = Path(sys.argv[1]), read_token()
set_panel_mode(ws, 'dev', token=key)
try:
    Path(sys.argv[2]).write_bytes(dev_path(ws).read_bytes())
except FileNotFoundError:
    pass
set_panel_mode(ws, 'ask_first', token=key)
"""
    # Reading a workspace record may race another Off; the switch itself is
    # serialized by the trusted per-workspace lock. Save records beforehand too.
    token = load_or_create_token()
    dev.enable_dev(ws, token=token)
    before = dev.dev_path(ws).read_bytes()
    workers = [subprocess.Popen([sys.executable, "-c", script, str(ws), str(tmp_path / f"record-{i}.json")],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=os.environ.copy()) for i in range(2)]
    for worker in workers:
        _, stderr = worker.communicate(timeout=30)
        assert worker.returncode == 0, stderr
    assert not dev.active_dev(ws, token=token)
    dev.dev_path(ws).write_bytes(before)
    assert not dev.active_dev(ws, token=token)
    for saved in tmp_path.glob("record-*.json"):
        dev.dev_path(ws).write_bytes(saved.read_bytes())
        assert not dev.active_dev(ws, token=token)


def test_look_only_and_filesystem_scope_never_relaxed(tmp_path):
    gate = _gate(tmp_path, "look_only")
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    assert not gate.dev_mode and gate.approval_mode == "look_only"
    with pytest.raises(Exception, match="Look only"):
        gate.claim_action(SET, {})
    workspace = WorkspaceMonitor([gate.workspace_dir])
    with pytest.raises(Exception, match="outside"):
        workspace.assert_in_workspace(tmp_path / "outside.rfa")


def _approved(gate):
    args = {"element_id": 1, "parameter_name": "Comments", "value": "changed"}
    plan = gate.create_plan([{"tool": SET, "arguments": args}], [{}])
    human_approve(gate, plan["plan_id"])
    return plan["plan_id"], {**args, "plan_id": plan["plan_id"]}


def test_dev_unplanned_writes_allowed_but_supplied_plan_consumed_once(tmp_path):
    gate = _gate(tmp_path)
    pid, args = _approved(gate)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    assert gate.claim_action(SET, {}) is None
    assert gate.claim_action(SET, args)["plan_id"] == pid
    with pytest.raises(Exception, match="remaining approved action"):
        gate.claim_action(SET, args)


def test_dev_refuses_tampered_and_unknown_supplied_plans(tmp_path):
    gate = _gate(tmp_path)
    pid, args = _approved(gate)
    plan = gate.load_plan(pid)
    plan["actions"][0]["arguments"]["value"] = "tampered"
    gate.save_plan(plan)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    with pytest.raises(Exception, match="changed after"):
        gate.claim_action(SET, args)
    with pytest.raises(Exception, match="does not exist"):
        gate.claim_action(SET, {"plan_id": "plan_" + "0" * 12})


def test_off_to_dev_during_authorization_cannot_allow_unaudited_write(tmp_path, monkeypatch):
    gate = _gate(tmp_path)
    observed = []
    read_state = approval_module.active_dev
    def enable_after_observation(*args, **kwargs):
        value = read_state(*args, **kwargs)
        observed.append(value)
        if len(observed) == 1:
            dev.enable_dev(gate.workspace_dir, token=TOKEN)
        return value
    monkeypatch.setattr(approval_module, "active_dev", enable_after_observation)
    with pytest.raises(Exception, match="requires a valid 'plan_id'"):
        gate.claim_action(SET, {})
    assert observed == [False]
    assert read_state(gate.workspace_dir, token=TOKEN)
    assert not gate.workspace_dir.joinpath(dev.AUDIT_FILENAME).exists()


def test_dev_to_off_keeps_strict_plan_check_and_audit_from_snapshot(tmp_path, monkeypatch):
    gate = _gate(tmp_path)
    pid, args = _approved(gate)
    plan = gate.load_plan(pid)
    plan["actions"][0]["arguments"]["value"] = "tampered"
    gate.save_plan(plan)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    observed = []
    read_state = approval_module.active_dev
    def disable_after_observation(*a, **kw):
        value = read_state(*a, **kw)
        observed.append(value)
        if len(observed) == 1:
            dev.disable_dev(gate.workspace_dir)
        return value
    monkeypatch.setattr(approval_module, "active_dev", disable_after_observation)
    with pytest.raises(Exception, match="changed after"):
        gate.claim_action(SET, args)
    assert observed == [True]
    assert not read_state(gate.workspace_dir, token=TOKEN)
    entries = [json.loads(line) for line in gate.workspace_dir.joinpath(dev.AUDIT_FILENAME).read_text().splitlines()]
    assert len(entries) == 1 and entries[0]["tool"] == SET and entries[0]["mutating"] is True


def test_every_dev_read_and_write_logged_and_secrets_redacted(tmp_path):
    gate = _gate(tmp_path)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    registry = SimpleNamespace(lookup_tool=lambda n: SimpleNamespace(is_mutating=n == SET),
                               lookup_tool_provider=lambda n: None)
    gate_before(registry, gate, "revit_get_context", {"password": "private", "file": "C:/secret/model.rvt"})
    gate_before(registry, gate, SET, {"value": "safe", "api_key": "private"})
    entries = [json.loads(line) for line in gate.workspace_dir.joinpath(dev.AUDIT_FILENAME).read_text().splitlines()]
    assert [e["tool"] for e in entries] == ["revit_get_context", SET]
    assert [e["mutating"] for e in entries] == [False, True]
    assert all(e["event"] == "call" for e in entries)
    raw = json.dumps(entries)
    assert "private" not in raw and "C:/secret" not in raw
    assert "safe" in raw


def test_audit_failure_blocks_execution(tmp_path):
    gate = _gate(tmp_path)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    gate.workspace_dir.joinpath(dev.AUDIT_FILENAME).mkdir()
    calls = []
    async def execute(name, args):
        calls.append(name)
    provider = SimpleNamespace(execute_tool=execute)
    registry = SimpleNamespace(lookup_tool=lambda n: SimpleNamespace(is_mutating=True),
                               lookup_tool_provider=lambda n: provider)
    with pytest.raises(OSError):
        asyncio.run(run_gated_tool(registry, gate, SET, {}))
    assert calls == []


def test_context_exposes_dev_without_expiry(tmp_path):
    gate = _gate(tmp_path)
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    server = get_context(None, live=False, approval_mode="ask_first", approval=gate.approval_state())["server"]
    assert server["dev_mode"] is True and server["approval_mode"] == "auto"
    assert server["auto_expires_at"] is None


def test_dev_preserves_read_guard_and_human_only_tools(tmp_path):
    registry, approval, _, _, _ = build_registry(WorkspaceMonitor([tmp_path / "ws"]))
    gate = approval.gate
    gate.override_token = TOKEN
    dev.enable_dev(gate.workspace_dir, token=TOKEN)
    with pytest.raises(ReadModeViolation):
        gate_before(registry, gate, "revit_execute_python", {"mode": "read", "script": "Transaction(doc, 'x')"})
    with pytest.raises(Exception, match="not available to AI"):
        gate_before(registry, gate, "approve_plan", {})
    assert gate_before(registry, gate, "revit_execute_python", {"mode": "read", "script": "print(doc.Title)"}) is None


@pytest.fixture
def hub(tmp_path):
    server = build_server(port=0, workspace=WorkspaceMonitor([tmp_path / "ws"]))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], load_or_create_token(), tmp_path / "ws", server
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _call(hub, mode=None, *, token=True, extra_headers=None, **fields):
    port, key, _, _ = hub
    headers = {"Content-Type": "application/json", **(extra_headers or {})}
    if token:
        headers["X-AMB-Token"] = key if token is True else token
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        data = json.dumps({"mode": mode, **fields}) if mode is not None else None
        conn.request("POST" if mode is not None else "GET", "/approval-mode" if mode is not None else "/diagnostics",
                     body=data, headers=headers)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read())
    finally:
        conn.close()


def test_panel_dev_auth_confirmation_and_origin_checks(hub):
    assert _call(hub, "dev", token=False, confirm=True)[0] == 401
    assert _call(hub, "dev", token="invalid", confirm=True)[0] == 401
    assert _call(hub, "dev", confirm=True, extra_headers={"Origin": "https://evil.example"})[0] == 403
    assert _call(hub, "dev", confirm=True, extra_headers={"Host": "evil.example"})[0] == 403
    assert _call(hub, "dev")[0] == 400
    assert _call(hub, "dev", confirm=True, extra_directory="C:/")[0] == 400
    assert _call(hub)[1]["dev_mode"] is False


def test_panel_switches_dev_on_and_off_with_shared_state_and_audit(hub):
    _, _, ws, _ = hub
    assert _call(hub, "dev", confirm=True)[0] == 200
    state = _call(hub)[1]
    assert state["dev_mode"] and state["approval_mode"] == "auto" and state["auto_expires_at"] is None
    other = ApprovalGate(ws, "ask_first")
    assert other.dev_mode
    assert _call(hub, "ask_first")[1]["approval_mode"] == "ask_first"
    assert not other.dev_mode
    entries = [json.loads(line) for line in ws.joinpath(dev.AUDIT_FILENAME).read_text().splitlines()]
    assert [(e["event"], e["mode"]) for e in entries] == [("toggle_requested", "dev"), ("toggle_requested", "ask_first")]


def test_panel_auto_retains_expiry_and_switching_modes_clears_other_override(hub):
    _, token, ws, _ = hub
    before = _call(hub, "auto", minutes=5, confirm=True)[1]
    assert not before["dev_mode"] and before["auto_expires_at"]
    assert auto.active_override(ws, token=token)["expires_at"] == before["auto_expires_at"]
    assert _call(hub, "dev", confirm=True)[1]["auto_expires_at"] is None
    assert auto.active_override(ws, token=token) is None
    switched = _call(hub, "auto", minutes=5, confirm=True)[1]
    assert switched["auto_expires_at"] and not switched["dev_mode"]
    assert not dev.active_dev(ws, token=token)
    assert _call(hub, "ask_first")[1]["approval_mode"] == "ask_first"


def test_panel_cannot_enable_dev_in_configured_look_only(hub):
    server = hub[3]
    server.RequestHandlerClass.approval_provider.gate.approval_mode = "look_only"
    assert _call(hub, "dev", confirm=True)[0] == 409
    assert _call(hub)[1]["dev_mode"] is False
