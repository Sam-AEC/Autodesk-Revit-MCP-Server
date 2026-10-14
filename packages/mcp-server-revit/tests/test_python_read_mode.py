"""revit_execute_python mode='read': no approval prompt, but it can never open a transaction.

Write mode (the default) keeps the full approval gate (ADR 0008/0017). Read mode is a
safety rail, not a security boundary, so these tests pin both halves of the contract.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from revit_mcp_server import mcp_server
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.registry_factory import build_registry
from revit_mcp_server.security import read_mode
from revit_mcp_server.security.gating import requires_approval
from revit_mcp_server.security.read_mode import (
    ReadModeViolation,
    execute_python_payload,
    is_read_mode_call,
    normalize_mode,
    validate_read_script,
)
from revit_mcp_server.security.workspace import WorkspaceMonitor

REPO_ROOT = Path(__file__).resolve().parents[3]
PROVIDER_SOURCE = REPO_ROOT / "packages" / "revit-bridge-addin" / "src" / "Bridge" / "PythonScriptRunner.cs"

AUDIT_SCRIPT = (
    "from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory\n"
    "walls = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()\n"
    "print(walls.GetElementCount())\n"
)


@pytest.fixture
def stack(tmp_path):
    registry, approval, job_manager, _modules, _ws = build_registry(WorkspaceMonitor([tmp_path]))
    approval.gate.approval_mode = "required"
    previous = (mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager)
    mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = registry, approval, job_manager
    try:
        yield registry, approval
    finally:
        mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = previous


def _call(name, arguments):
    result = asyncio.run(mcp_server.call_tool(name, arguments))
    content = result.content if hasattr(result, "content") else result
    return content[0].text


@pytest.mark.parametrize(
    "snippet",
    [
        "t = Transaction(doc, 'x')\nt.Start()",
        "from Autodesk.Revit.DB import Transaction",
        "import Autodesk.Revit.DB as DB\nt = DB.Transaction(doc, 'x')",
        "g = TransactionGroup(doc)",
        "s = SubTransaction(doc)\ns.Start()",
        "exec('print 1')",
        "x = eval('1+1')",
        "m = __import__('Autodesk')",
        "doc.Save()",
        "doc.SaveAs(path)",
        "app.SynchronizeWithCentral",
    ],
)
def test_read_mode_rejects_transaction_text_and_writers(snippet):
    with pytest.raises(ReadModeViolation):
        validate_read_script(snippet)


def test_read_mode_accepts_plain_inspection_and_lookalike_names():
    validate_read_script(AUDIT_SCRIPT)
    validate_read_script("import re\npat = re.compile('a')\nstatus = TransactionStatus.Committed")
    validate_read_script("print('the executor ran')")


@pytest.mark.parametrize("bad", [None, "", "   ", 5])
def test_read_mode_needs_a_script(bad):
    with pytest.raises(ReadModeViolation):
        validate_read_script(bad)


def test_mode_defaults_to_write_and_rejects_unknown_values():
    assert normalize_mode(None) == "write"
    assert normalize_mode(" READ ") == "read"
    with pytest.raises(ValueError):
        normalize_mode("readonly")


def test_payload_always_carries_the_mode():
    assert execute_python_payload({"script": "print 1"}) == {"script": "print 1", "mode": "write"}
    assert execute_python_payload({"script": AUDIT_SCRIPT, "mode": "read"})["mode"] == "read"
    with pytest.raises(ReadModeViolation):
        execute_python_payload({"script": "Transaction(doc, 'x')", "mode": "read"})
    with pytest.raises(ValueError):
        execute_python_payload({"script": "print 1", "mode": "maybe"})


def test_is_read_mode_call_fails_closed():
    assert is_read_mode_call({"script": AUDIT_SCRIPT, "mode": "read"}) is True
    assert is_read_mode_call({"script": AUDIT_SCRIPT}) is False
    assert is_read_mode_call({"script": AUDIT_SCRIPT, "mode": "write"}) is False
    assert is_read_mode_call({"script": AUDIT_SCRIPT, "mode": "bogus"}) is False
    assert is_read_mode_call(None) is False
    assert is_read_mode_call("read") is False


def test_write_mode_still_needs_an_approved_plan(stack):
    registry, approval = stack
    tool = registry.lookup_tool("revit_execute_python")
    assert tool.is_mutating and tool.destructive

    for arguments in ({"script": "print 1"}, {"script": "print 1", "mode": "write"}):
        assert requires_approval(registry, "revit_execute_python", tool, arguments) is True
        text = _call("revit_execute_python", arguments)
        assert text.startswith("Approval Gate Blocked"), text
        assert "plan_id" in text


def test_write_mode_runs_with_an_approved_plan(stack):
    registry, approval = stack
    plan = approval.gate.create_plan(
        [{"tool": "revit_execute_python", "arguments": {"script": "print 1"}}], [{}]
    )
    approval.gate.update_plan_state(
        plan["plan_id"], "approved", approver="test", via="cli", expected_hash=plan["plan_hash"]
    )
    text = _call("revit_execute_python", {"script": "print 1", "plan_id": plan["plan_id"]})
    assert "executed successfully" in text
    assert '"mode": "write"' in text


def test_read_mode_runs_without_a_plan_and_sends_the_mode(stack):
    registry, approval = stack
    tool = registry.lookup_tool("revit_execute_python")
    arguments = {"script": AUDIT_SCRIPT, "mode": "read"}
    assert requires_approval(registry, "revit_execute_python", tool, arguments) is False
    text = _call("revit_execute_python", arguments)
    assert "executed successfully" in text
    assert '"mode": "read"' in text
    assert approval.gate.list_pending_plans() == []


def test_read_mode_with_transaction_text_is_rejected_before_it_reaches_revit(stack):
    registry, approval = stack
    tool = registry.lookup_tool("revit_execute_python")
    arguments = {"script": "t = Transaction(doc, 'x')\nt.Start()", "mode": "read"}
    with pytest.raises(ReadModeViolation):
        requires_approval(registry, "revit_execute_python", tool, arguments)
    text = _call("revit_execute_python", arguments)
    assert "executed successfully" not in text
    assert "Read mode refuses" in text
    assert approval.gate.list_pending_plans() == []
    # asking for read mode does not get the script past the gate either
    provider = registry.lookup_tool_provider("revit_execute_python")
    with pytest.raises(ReadModeViolation):
        asyncio.run(provider.execute_tool("revit_execute_python", arguments))


def test_gate_failure_is_a_bridge_error_not_a_silent_pass(stack):
    _, approval = stack
    with pytest.raises(BridgeError):
        approval.gate.check_tool_execution("revit_execute_python", {"script": "print 1"})


def test_other_mutating_tools_ignore_a_mode_argument(stack):
    registry, _ = stack
    tool = registry.lookup_tool("revit_create_wall")
    assert requires_approval(registry, "revit_create_wall", tool, {"mode": "read"}) is True
    assert requires_approval(registry, "revit_list_levels", registry.lookup_tool("revit_list_levels"), {}) is False


def test_tool_annotations_do_not_claim_read_only(stack):
    registry, _ = stack
    listed = {t.name: t for t in asyncio.run(mcp_server.list_tools())}
    python = listed["revit_execute_python"]
    assert python.annotations.readOnlyHint is False
    assert python.annotations.destructiveHint is True
    assert "plan_id" in python.inputSchema["properties"]
    mode = python.inputSchema["properties"]["mode"]
    assert mode["enum"] == ["read", "write"] and mode["default"] == "write"
    assert "boundary" in mode["description"]


def test_python_and_addin_forbidden_token_lists_agree():
    """The add-in repeats the Python rules; a rule added on one side must be added on the other."""
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    for name, _pattern in read_mode.FORBIDDEN_IN_READ_MODE:
        assert re.search(rf'"{re.escape(name)}"', source), f"{name} missing from PythonScriptRunner.cs"


def test_look_only_mode_still_allows_read_mode_scripts_but_not_write_scripts(stack):
    from revit_mcp_server.security.dispatch import gate_before

    registry, approval = stack
    approval.gate.approval_mode = "look_only"
    assert gate_before(registry, approval.gate, "revit_execute_python", {"script": AUDIT_SCRIPT, "mode": "read"}) is None
    with pytest.raises(BridgeError, match="Look only mode"):
        gate_before(registry, approval.gate, "revit_execute_python", {"script": AUDIT_SCRIPT})
    with pytest.raises(ReadModeViolation):
        gate_before(registry, approval.gate, "revit_execute_python", {"script": "Transaction(doc, 'x')", "mode": "read"})


def test_run_job_gate_follows_the_wrapped_call(stack):
    registry, _ = stack
    tool = registry.lookup_tool("revit_run_job")
    assert tool.is_mutating
    gated = lambda args: requires_approval(registry, "revit_run_job", tool, args)  # noqa: E731
    assert gated({"script": AUDIT_SCRIPT, "mode": "read"}) is False
    assert gated({"script": AUDIT_SCRIPT}) is True
    assert gated({"command": "revit_list_levels"}) is False
    assert gated({"command": "revit_create_wall", "args": {}}) is True
    assert gated({}) is True  # malformed stays gated
    assert gated({"command": "nope"}) is True
    with pytest.raises(ReadModeViolation):
        gated({"script": "Transaction(doc, 'x')", "mode": "read"})
