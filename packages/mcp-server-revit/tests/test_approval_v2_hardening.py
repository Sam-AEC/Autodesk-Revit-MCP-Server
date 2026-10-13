"""Approval v2 hardening: approval stays human-only on every dispatch path, an approval
covers exactly the plan content that was shown, and each approved action runs at most once."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import threading

import pytest

from helpers import human_approve, panel_decide
from revit_mcp_server import approve_cli, mcp_server, panel_server
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.registry_factory import build_registry
from revit_mcp_server.security.approval import (
    ApprovalGate,
    canonical_arguments,
    local_user,
    normalize_approval_mode,
    plan_hash,
)
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.workspace import WorkspaceMonitor

SET = "revit_set_parameter_value"


def _args(element_id=1, value="60"):
    return {"element_id": element_id, "parameter_name": "FireRating", "value": value}


@pytest.fixture
def server(tmp_path):
    registry, approval, job_manager, _m, _w = build_registry(WorkspaceMonitor([tmp_path]))
    approval.gate.approval_mode = "required"
    previous = (mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager)
    mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = registry, approval, job_manager
    yield registry, approval
    mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = previous


def _call(name, args):
    result = asyncio.run(mcp_server.call_tool(name, args))
    return (result.content if hasattr(result, "content") else result)[0].text


def _draft(approval, *action_args, tool=SET):
    plan = asyncio.run(approval.execute_tool(
        "plan_actions", {"actions": [{"tool": tool, "arguments": a} for a in action_args]}))
    return plan["plan_id"]


# ---- F1: human-only tools are refused on every internal path ----------------------


@pytest.mark.parametrize("tool", ["approve_plan", "reject_plan", "rollback_plan"])
def test_recipe_step_cannot_run_a_human_only_tool(server, tmp_path, tool):
    registry, approval = server
    pid = _draft(approval, _args())
    (tmp_path / "r.yaml").write_text(
        f"id: r\nsteps:\n  - id: s1\n    tool: {tool}\n"
        f"    args: {{plan_id: {pid}, approver: Sam, approved_via: cli}}\n", encoding="utf-8")
    _call("recipe_runner_run_recipe", {"recipe_id": "r.yaml"})
    plan = approval.gate.load_plan(pid)
    assert plan["state"] == "pending"
    assert "approved_via" not in plan and "approved_by" not in plan


def test_module_tool_executor_refuses_approve_plan(server):
    registry, approval = server
    pid = _draft(approval, _args())
    module_provider = registry.get_provider("module")
    with pytest.raises(BridgeError, match="not available to AI clients"):
        asyncio.run(module_provider._execute_registered_tool("approve_plan", {"plan_id": pid}))
    assert approval.gate.load_plan(pid)["state"] == "pending"


@pytest.mark.parametrize("tool", ["approve_plan", "reject_plan", "rollback_plan"])
def test_generic_provider_path_refuses_human_only_tools(server, tool):
    registry, approval = server
    pid = _draft(approval, _args())
    with pytest.raises(BridgeError):
        asyncio.run(approval.execute_tool(tool, {"plan_id": pid}))
    with pytest.raises(BridgeError):
        asyncio.run(run_gated_tool(registry, approval.gate, tool, {"plan_id": pid}))
    assert approval.gate.load_plan(pid)["state"] == "pending"


def test_a_plan_cannot_contain_a_human_only_action(server):
    _, approval = server
    with pytest.raises(BridgeError, match="cannot be part of a plan"):
        _draft(approval, {"plan_id": "plan_000000000000"}, tool="approve_plan")


def test_spoofed_approved_via_and_approver_arguments_are_ignored(server):
    registry, approval = server
    pid = _draft(approval, _args())
    done = asyncio.run(panel_decide(approval, "approve_plan", pid, approver="Site Lead", approved_via="cli"))
    assert done["approved_via"] == "panel"
    assert done["approved_by"] == local_user()


def test_panel_route_records_panel_even_if_the_request_says_cli(server):
    registry, approval = server
    pid = _draft(approval, _args())
    args = {"plan_id": pid, "approver": "Site Lead", "approved_via": "cli",
            "expected_hash": approval.gate.load_plan(pid)["plan_hash"]}
    done = panel_server._run_tool_sync(registry, approval, "approve_plan", args)
    assert done["approved_via"] == "panel" and done["approved_by"] == local_user()


def test_update_plan_state_refuses_an_unknown_channel(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    with pytest.raises(ValueError, match="panel or the command-line tool"):
        gate.update_plan_state(pid, "approved", via="mcp", expected_hash=plan_hash(gate.load_plan(pid)))


# ---- F2: plan ids cannot name files outside the plans folder ---------------------


FORGED = {"plan_id": "x", "state": "approved",
          "actions": [{"action_id": "a", "tool": "revit_delete_element",
                       "arguments": {"element_id": 7}, "state": "pending"}]}


@pytest.mark.parametrize("bad", ["../exports/f", "plan_ABC", "plan_123", "plan_0123456789ab/../x", "", None, 5])
def test_malformed_plan_ids_are_refused(server, tmp_path, bad):
    _, approval = server
    (tmp_path / "exports").mkdir(exist_ok=True)
    (tmp_path / "exports" / "f.json").write_text(json.dumps(FORGED), encoding="utf-8")
    gate = approval.gate
    with pytest.raises(BridgeError):
        gate.load_plan(bad)
    with pytest.raises(BridgeError):
        gate.check_tool_execution("revit_delete_element", {"element_id": 7, "plan_id": bad or "x/../y"})
    with pytest.raises((BridgeError, ValueError)):
        gate.update_plan_state(bad, "approved", via="cli", expected_hash="sha256:0")


def test_absolute_plan_id_cannot_unlock_a_forged_file(server, tmp_path):
    _, approval = server
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(FORGED), encoding="utf-8")
    out = _call("revit_delete_element", {"element_id": 7, "plan_id": str(forged.with_suffix(""))})
    assert "Approval Gate Blocked" in out and "Invalid plan_id" in out
    out = _call("revit_delete_element", {"element_id": 7, "plan_id": "../exports/f"})
    assert "Approval Gate Blocked" in out


def test_plan_file_holding_a_different_plan_id_is_refused(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    other = "plan_0123456789ab"
    (gate.plans_dir / f"{other}.json").write_text((gate.plans_dir / f"{pid}.json").read_text(), encoding="utf-8")
    with pytest.raises(BridgeError, match="does not hold that plan"):
        gate.load_plan(other)
    assert all(p["plan_id"] == pid for p in gate.list_pending_plans())


def test_cli_refuses_a_path_as_plan_id(tmp_path, capsys):
    assert approve_cli.main(["--workspace", str(tmp_path), "show", "../plans/x"]) == 1
    assert "Invalid plan_id" in capsys.readouterr().err


# ---- F3: approval binds to the content that was shown ----------------------------


def test_cli_approves_exactly_what_it_displayed(tmp_path, monkeypatch):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args(77)}], [{}])["plan_id"]
    path = gate.plans_dir / f"{pid}.json"

    def swap_then_confirm(_prompt):
        data = json.loads(path.read_text())
        data["actions"][0]["tool"] = "revit_delete_element"
        data["actions"][0]["arguments"] = {"element_id": 77}
        path.write_text(json.dumps(data))
        return pid

    stdin = io.StringIO()
    stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("builtins.input", swap_then_confirm)
    assert approve_cli.main(["--workspace", str(tmp_path), "approve", pid]) == 1
    assert gate.load_plan(pid)["state"] == "pending"


def test_approval_needs_the_hash_that_was_shown(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    for wrong in (None, "", "sha256:" + "0" * 64):
        with pytest.raises(ValueError, match="not the plan that was shown"):
            gate.update_plan_state(pid, "approved", via="cli", expected_hash=wrong)
    plan = gate.update_plan_state(pid, "approved", via="cli", expected_hash=plan_hash(gate.load_plan(pid)))
    assert plan["approved_hash"] == plan["plan_hash"] == plan_hash(plan)


def test_plan_edited_after_drafting_cannot_be_approved(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    plan = gate.load_plan(pid)
    plan["actions"][0]["arguments"]["value"] = "999"
    gate.save_plan(plan)
    with pytest.raises(ValueError, match="changed after it was drafted"):
        gate.update_plan_state(pid, "approved", via="cli", expected_hash=plan_hash(plan))


def test_plan_edited_on_disk_after_approval_is_refused_at_execution(server):
    _, approval = server
    pid = _draft(approval, _args(1, "60"))
    asyncio.run(panel_decide(approval, "approve_plan", pid))
    path = approval.gate.plans_dir / f"{pid}.json"
    data = json.loads(path.read_text())
    data["actions"][0]["tool"] = "revit_delete_element"
    data["actions"][0]["arguments"] = {"element_id": 999}
    path.write_text(json.dumps(data))

    out = _call("revit_delete_element", {"element_id": 999, "plan_id": pid})
    assert "changed after it was approved" in out
    with pytest.raises(BridgeError, match="changed after it was approved"):
        asyncio.run(approval.execute_tool("execute_plan", {"plan_id": pid}))
    assert approval.gate.load_plan(pid)["actions"][0]["state"] == "pending"


# ---- (a) terminal escapes, (b) malformed arguments -------------------------------


def test_escape_sequences_in_plan_text_are_shown_not_sent(tmp_path, capsys):
    gate = ApprovalGate(tmp_path, "required")
    plan = gate.create_plan([
        {"tool": "revit_delete_element", "arguments": {"element_id": 5}},
        {"tool": "revit_get_document_info\r\x1b[2K\x1b[1A  1. harmless", "arguments": {}},
        {"tool": "revit_get_document_info", "arguments": {"\x1b[8mhidden": "\x1b]0;title\x07‮\x9b"}},
    ], [{}, {}, {}])
    text = approve_cli.describe_plan(plan)
    for raw in ("\x1b", "\r", "\x07", "\x9b", "‮"):
        assert raw not in text
    assert "\\x1b[2K" in text and "\\x0d" in text
    assert approve_cli.main(["--workspace", str(tmp_path), "list"]) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_malformed_arguments_get_a_plain_message(tmp_path, monkeypatch, capsys):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    path = gate.plans_dir / f"{pid}.json"
    data = json.loads(path.read_text())
    data["actions"][0]["arguments"] = ["only a dry run"]
    data["plan_hash"] = plan_hash(data)
    path.write_text(json.dumps(data))

    text = approve_cli.describe_plan(gate.load_plan(pid))
    assert "MALFORMED ARGUMENTS" in text
    assert approve_cli.main(["--workspace", str(tmp_path), "approve", pid, "--yes"]) == 1
    assert "malformed" in capsys.readouterr().err
    assert gate.load_plan(pid)["state"] == "pending"


def test_non_object_arguments_are_refused_when_drafting_and_never_match(server):
    _, approval = server
    with pytest.raises(BridgeError, match="must be an object"):
        _draft(approval, ["not", "an", "object"])
    assert canonical_arguments(["x"]) != canonical_arguments({})


# ---- (c) at most once, (d) concurrency --------------------------------------------


def test_a_tool_that_raises_still_consumes_its_action(server):
    registry, approval = server
    provider = registry.lookup_tool_provider(SET)
    calls = []

    async def applies_then_raises(name, arguments):
        calls.append(arguments)
        raise TimeoutError("bridge timeout after the change was applied")

    pid = _draft(approval, _args())
    asyncio.run(panel_decide(approval, "approve_plan", pid))
    provider.execute_tool, original = applies_then_raises, provider.execute_tool
    try:
        for _ in range(3):
            _call(SET, {**_args(), "plan_id": pid})
    finally:
        provider.execute_tool = original
    assert len(calls) == 1
    plan = approval.gate.load_plan(pid)
    assert plan["actions"][0]["state"] == "failed"
    assert plan["state"] == "partial"


def test_concurrent_claims_let_exactly_one_win(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    human_approve(gate, pid)
    wins, losses = [], []
    start = threading.Barrier(12)

    def worker():
        other = ApprovalGate(tmp_path, "required")  # separate gate objects share only the files
        start.wait()
        try:
            wins.append(other.claim_action(SET, {**_args(), "plan_id": pid}))
        except BridgeError:
            losses.append(1)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1 and len(losses) == 11


def test_concurrent_mcp_calls_run_one_approved_action_once(server):
    registry, approval = server
    tool = "selection_tools_set_selection"
    provider = registry.lookup_tool_provider(tool)
    ran = []

    async def slow(name, arguments):
        ran.append(1)
        await asyncio.sleep(0.05)
        return {"ok": True}

    args = {"element_uids": ["u1"]}
    pid = _draft(approval, args, tool=tool)
    asyncio.run(panel_decide(approval, "approve_plan", pid))
    provider.execute_tool, original = slow, provider.execute_tool
    try:
        async def many():
            return await asyncio.gather(*(mcp_server.call_tool(tool, {**args, "plan_id": pid}) for _ in range(5)))
        asyncio.run(many())
    finally:
        provider.execute_tool = original
    assert len(ran) == 1
    assert approval.gate.load_plan(pid)["state"] == "executed"


def test_editing_an_action_back_to_pending_does_not_reopen_it(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    human_approve(gate, pid)
    claim = gate.claim_action(SET, {**_args(), "plan_id": pid})
    gate.finish_action(claim, ok=True)
    plan = gate.load_plan(pid)
    plan["state"] = "approved"
    plan["actions"][0]["state"] = "pending"
    gate.save_plan(plan)
    with pytest.raises(BridgeError, match="does not approve this call"):
        gate.claim_action(SET, {**_args(), "plan_id": pid})


# ---- (e) withdraw an approval ------------------------------------------------------


def test_a_person_can_reject_an_approved_plan_before_it_runs(server):
    _, approval = server
    pid = _draft(approval, _args())
    asyncio.run(panel_decide(approval, "approve_plan", pid))
    done = asyncio.run(panel_decide(approval, "reject_plan", pid))
    assert done["state"] == "rejected" and done["rejected_after_approval"] is True
    assert "Approval Gate Blocked" in _call(SET, {**_args(), "plan_id": pid})


def test_an_executed_plan_cannot_be_rejected(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = gate.create_plan([{"tool": SET, "arguments": _args()}], [{}])["plan_id"]
    human_approve(gate, pid)
    gate.mark_action_executed(SET, {**_args(), "plan_id": pid})
    assert gate.load_plan(pid)["state"] == "executed"
    with pytest.raises(ValueError, match="only a pending or approved plan"):
        gate.update_plan_state(pid, "rejected", via="cli")


# ---- (f) approval_mode fails closed -----------------------------------------------


@pytest.mark.parametrize("mode", ["required", "Required", " required ", "REQUIRED", "bogus", "", None, "off"])
def test_approval_mode_other_than_auto_keeps_the_gate_on(tmp_path, mode):
    gate = ApprovalGate(tmp_path, mode)
    assert gate.approval_mode == "ask_first"
    with pytest.raises(BridgeError, match="requires a valid 'plan_id'"):
        gate.check_tool_execution("revit_delete_element", {"element_id": 1})


@pytest.mark.parametrize("mode", ["auto", " Auto "])
def test_only_auto_turns_the_gate_off(tmp_path, mode):
    gate = ApprovalGate(tmp_path, mode)
    assert gate.approval_mode == "auto"
    gate.check_tool_execution("revit_delete_element", {"element_id": 1})


def test_unknown_approval_mode_logs_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        assert normalize_approval_mode("bogus") == "ask_first"
    assert "treating it as 'ask_first'" in caplog.text
