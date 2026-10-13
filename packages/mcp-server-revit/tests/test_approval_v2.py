"""Approval v2, slice 1: a model cannot approve, widen or replay its own plans."""
from __future__ import annotations

import asyncio
import io
import json

import pytest

from revit_mcp_server import approve_cli, mcp_server
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.registry_factory import build_registry
from revit_mcp_server.security.approval import ApprovalGate, HUMAN_ONLY_TOOLS, local_user
from revit_mcp_server.security.workspace import WorkspaceMonitor
from helpers import panel_decide, human_approve

SET = "revit_set_parameter_value"


def _args(element_id=1, value="60"):
    return {"element_id": element_id, "parameter_name": "FireRating", "value": value}


def _approved(gate, *action_args):
    plan = gate.create_plan([{"tool": SET, "arguments": a} for a in action_args], [{} for _ in action_args])
    human_approve(gate, plan["plan_id"])
    return plan["plan_id"]


# ---- binding the call to the approved action -------------------------------------


def test_approved_plan_does_not_unlock_a_different_tool(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = _approved(gate, _args())
    with pytest.raises(BridgeError, match="does not approve this call"):
        gate.check_tool_execution("revit_delete_elements", {**_args(), "plan_id": pid})


def test_approved_plan_does_not_unlock_different_arguments(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = _approved(gate, _args(1, "60"))
    for other in (_args(2, "60"), _args(1, "999")):
        with pytest.raises(BridgeError, match="does not approve this call"):
            gate.check_tool_execution(SET, {**other, "plan_id": pid})
    # same call, different key order and 60.0 vs 60 still matches; volatile keys are ignored
    gate.check_tool_execution(SET, {"value": "60", "parameter_name": "FireRating", "element_id": 1.0,
                                    "plan_id": pid, "run_async": True, "idempotency_key": "k"})


def test_replaying_an_executed_action_is_refused(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = _approved(gate, _args(1), _args(2))
    call = {**_args(1), "plan_id": pid}
    gate.check_tool_execution(SET, call)
    gate.mark_action_executed(SET, call)
    assert gate.load_plan(pid)["state"] == "approved"  # one action still open
    with pytest.raises(BridgeError, match="does not approve this call"):
        gate.check_tool_execution(SET, call)
    gate.mark_action_executed(SET, {**_args(2), "plan_id": pid})
    assert gate.load_plan(pid)["state"] == "executed"


def test_duplicate_actions_each_run_once(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = _approved(gate, _args(1), _args(1))
    call = {**_args(1), "plan_id": pid}
    for _ in range(2):
        gate.check_tool_execution(SET, call)
        gate.mark_action_executed(SET, call)
    assert gate.load_plan(pid)["state"] == "executed"


def test_cannot_approve_an_executed_plan_again(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    pid = _approved(gate, _args())
    gate.mark_action_executed(SET, {**_args(), "plan_id": pid})
    with pytest.raises(ValueError, match="only a pending plan"):
        human_approve(gate, pid)


# ---- MCP surface -----------------------------------------------------------------


@pytest.fixture
def server(tmp_path):
    registry, approval, job_manager, _m, _w = build_registry(WorkspaceMonitor([tmp_path]))
    approval.gate.approval_mode = "required"
    previous = (mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager)
    mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = registry, approval, job_manager
    yield registry, approval
    mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = previous


def test_mcp_tool_list_hides_human_only_tools_but_registry_keeps_them(server):
    registry, _ = server
    listed = {t.name for t in asyncio.run(mcp_server.list_tools())}
    registered = {t.name for t in registry.get_all_tools()}
    assert HUMAN_ONLY_TOOLS == {"approve_plan", "reject_plan", "rollback_plan"}
    assert not (listed & HUMAN_ONLY_TOOLS)
    assert HUMAN_ONLY_TOOLS <= registered
    assert registered - listed == HUMAN_ONLY_TOOLS
    assert "plan_actions" in listed and "execute_plan" in listed


def test_mcp_call_of_a_hidden_tool_is_refused(server):
    _, approval = server
    plan = asyncio.run(approval.execute_tool("plan_actions", {"actions": [{"tool": SET, "arguments": _args()}]}))
    out = asyncio.run(mcp_server.call_tool("approve_plan", {"plan_id": plan["plan_id"]}))
    assert out.isError
    assert "not available to AI clients" in out.content[0].text
    assert approval.gate.load_plan(plan["plan_id"])["state"] == "pending"


def test_server_instructions_tell_the_model_to_stop_and_ask():
    text = mcp_server.SERVER_INSTRUCTIONS
    assert "STOP and ask the person" in text
    assert "aec-model-bridge-approve" in text
    assert "have the human approve it (approve_plan" not in text


def test_registry_provider_can_still_approve_for_the_panel(server):
    _, approval = server
    plan = asyncio.run(approval.execute_tool("plan_actions", {"actions": [{"tool": SET, "arguments": _args()}]}))
    done = asyncio.run(panel_decide(approval, "approve_plan", plan["plan_id"]))
    assert done["state"] == "approved" and done["approved_via"] == "panel"


def test_run_async_path_marks_the_action_executed(server):
    _, approval = server
    gate = approval.gate
    plan = asyncio.run(approval.execute_tool("plan_actions", {"actions": [{"tool": SET, "arguments": _args()}]}))
    pid = plan["plan_id"]
    asyncio.run(panel_decide(approval, "approve_plan", pid))
    call = {**_args(), "plan_id": pid, "run_async": True}

    async def go():
        first = await mcp_server.call_tool(SET, call)
        second = await mcp_server.call_tool(SET, call)
        await mcp_server.job_manager.shutdown(cancel_running=False)
        return first, second

    first, second = asyncio.run(go())
    assert "queued" in first[0].text
    assert gate.load_plan(pid)["state"] == "executed"
    assert second.isError
    assert "Approval Gate Blocked" in second.content[0].text


# ---- command-line approval -------------------------------------------------------


def _pending(tmp_path):
    gate = ApprovalGate(tmp_path, "required")
    plan = gate.create_plan([{"tool": SET, "arguments": _args(77)}], [{"77": {"FireRating": "30"}}])
    return gate, plan["plan_id"]


def test_cli_list_show_approve_round_trip(tmp_path, monkeypatch, capsys):
    gate, pid = _pending(tmp_path)
    ws = ["--workspace", str(tmp_path)]
    assert approve_cli.main(ws + ["list"]) == 0
    assert pid in capsys.readouterr().out
    assert approve_cli.main(ws + ["show", pid]) == 0
    shown = capsys.readouterr().out
    assert SET in shown and "77" in shown and "Actions: 1" in shown

    stdin = io.StringIO(pid + "\n")
    stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", stdin)
    assert approve_cli.main(ws + ["approve", pid]) == 0
    plan = gate.load_plan(pid)
    assert plan["state"] == "approved"
    assert plan["approved_by"] == local_user() and plan["approved_via"] == "cli" and plan["approved_at"]
    # an approved plan cannot be approved again, but a person can still withdraw it
    assert approve_cli.main(ws + ["approve", pid, "--yes"]) == 1
    assert approve_cli.main(ws + ["reject", pid, "--yes"]) == 0
    assert gate.load_plan(pid)["state"] == "rejected"


def test_cli_wrong_confirmation_leaves_plan_pending(tmp_path, monkeypatch):
    gate, pid = _pending(tmp_path)
    stdin = io.StringIO("yes\n")
    stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", stdin)
    assert approve_cli.main(["--workspace", str(tmp_path), "approve", pid]) == 2
    assert gate.load_plan(pid)["state"] == "pending"


def test_cli_reject_round_trip(tmp_path, monkeypatch):
    gate, pid = _pending(tmp_path)
    stdin = io.StringIO(pid + "\n")
    stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", stdin)
    assert approve_cli.main(["--workspace", str(tmp_path), "reject", pid]) == 0
    plan = gate.load_plan(pid)
    assert plan["state"] == "rejected" and plan["rejected_via"] == "cli"


def test_cli_refuses_non_interactive_input_without_yes(tmp_path, monkeypatch, capsys):
    gate, pid = _pending(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(pid + "\n"))  # piped: isatty() is False
    assert approve_cli.main(["--workspace", str(tmp_path), "approve", pid]) == 2
    assert "without a terminal" in capsys.readouterr().err
    assert gate.load_plan(pid)["state"] == "pending"
    assert approve_cli.main(["--workspace", str(tmp_path), "approve", pid, "--yes"]) == 0
    assert gate.load_plan(pid)["state"] == "approved"


def test_cli_approval_keeps_the_proof_bundle_working(tmp_path):
    gate, pid = _pending(tmp_path)
    assert approve_cli.main(["--workspace", str(tmp_path), "approve", pid, "--yes"]) == 0
    gate.mark_action_executed(SET, {**_args(77), "plan_id": pid})
    proof = json.loads((tmp_path / "proofs" / f"{pid}.json").read_text(encoding="utf-8"))
    assert proof["approved_by"] == local_user()
