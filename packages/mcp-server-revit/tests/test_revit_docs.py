from __future__ import annotations

import asyncio
import contextvars
import json
from types import SimpleNamespace

import pytest

from helpers import human_approve
from revit_mcp_server.check_contract import parse_script_output
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest
from revit_mcp_server.modules.revit_docs import module as docs
from revit_mcp_server.providers.module_provider import ModuleProvider
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.module_execution import authorized_module_execution, module_execution_authorized
from revit_mcp_server.security.workspace import WorkspaceMonitor


SUCCESS = "SUMMARY\tcreated\nMETA\toutcome\tok\nMETA\tchanged_ids\t12\nROW\trow_type=post\tcheck=exists\tok=1\tdetail=id 12\nCOUNT\tfail\t0"
RID = "11223344-5566-7788-99aa-bbccddeeff00"


def wire(tmp_path, monkeypatch, mode="ask_first", raw=None):
    inst = ModuleInstance(ModuleManifest(**json.loads((docs.MODULE_DIR / "module.json").read_text(encoding="utf-8"))), docs.MODULE_DIR)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    modules = SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False))
    gate = ApprovalGate(tmp_path, mode)

    class FakeRevit:
        def __init__(self):
            self.calls = []

        async def execute_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return raw if raw is not None else {"success": True, "output": SUCCESS}

        def call_is_read_only(self, name, arguments):
            return arguments.get("mode") == "read"

    revit = FakeRevit()
    provider = ModuleProvider(modules, WorkspaceMonitor([tmp_path]))
    capabilities = {tool.name: tool for tool in provider.get_capabilities()}
    capabilities["revit_execute_python"] = SimpleNamespace(is_mutating=True)
    registry = SimpleNamespace(
        lookup_tool=lambda name: capabilities.get(name),
        lookup_tool_provider=lambda name: provider if name in capabilities and name != "revit_execute_python" else revit,
        get_provider=lambda name: SimpleNamespace(gate=gate) if name == "approval" else None,
    )
    provider.tool_registry = registry
    return provider, gate, registry, revit, inst


def approved(gate, tool, arguments):
    plan = gate.create_plan([{"tool": tool, "arguments": arguments}], [{}])
    human_approve(gate, plan["plan_id"])
    return plan["plan_id"]


def test_public_tool_names_are_manifest_mcp_names(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    names = {t.name for t in provider.get_capabilities()}
    assert {"revit_make_view", "revit_make_sheet", "revit_make_schedule", "revit_export",
            "revit_render_check", "revit_list_views_sheets_schedules"} <= names
    assert not any(n.startswith("revit_docs_") for n in names)


@pytest.mark.parametrize("tool,args", [
    ("revit_make_view", {"kind": "3d", "name": "Review", "tag": "DOC"}),
    ("revit_export", {"format": "pdf", "view_ids": [1]}),
])
def test_one_outer_claim_authorizes_vetted_nested_python(tmp_path, monkeypatch, tool, args):
    if tool == "revit_export":
        args = {**args, "path": str(tmp_path / "review.pdf")}
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    pid = approved(gate, tool, args)
    result = asyncio.run(run_gated_tool(registry, gate, tool, {**args, "plan_id": pid}))
    assert result["ok"] is True
    assert len(revit.calls) == 1
    assert revit.calls[0][0] == "revit_execute_python"
    assert revit.calls[0][1]["mode"] == "write"
    assert len(gate.load_plan(pid)["actions"]) == 1
    assert gate.load_plan(pid)["actions"][0]["state"] == "executed"


def test_metadata_and_direct_nested_calls_do_not_grant_authority(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    args = {"kind": "3d", "name": "Review", "tag": "DOC"}
    pid = approved(gate, "revit_make_view", args)
    # Even an approved plan on disk grants nothing until dispatch claims it.
    result = asyncio.run(provider.execute_tool("revit_make_view", {**args, "plan_id": pid}))
    assert result["ok"] is False
    assert not revit.calls
    with pytest.raises(BridgeError, match="active authorized"):
        asyncio.run(provider._execute_approved_tool("revit_execute_python", {"mode": "write"}))
    assert not revit.calls


def test_copied_context_is_revoked_and_wrong_outer_name_is_denied():
    with authorized_module_execution("revit_make_view"):
        saved = contextvars.copy_context()
        assert saved.run(module_execution_authorized, "revit_make_view")
        assert not module_execution_authorized("revit_export")
    assert not saved.run(module_execution_authorized, "revit_make_view")


def test_saved_executor_cannot_use_later_scope_with_the_same_tool(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, mode="auto")

    async def scenario():
        with authorized_module_execution("revit_make_view"):
            old = provider._approved_tool_executor(asyncio.get_running_loop(), "revit_make_view")
        with authorized_module_execution("revit_make_view"):
            with pytest.raises(BridgeError, match="active authorized"):
                old("revit_execute_python", {"mode": "write"})
            fresh = provider._approved_tool_executor(asyncio.get_running_loop(), "revit_make_view")
            result = await asyncio.to_thread(fresh, "revit_execute_python", {"mode": "write"})
            assert result["success"] is True

    asyncio.run(scenario())
    assert len(revit.calls) == 1


def test_nested_dev_audit_failure_refuses_before_revit(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, mode="auto")
    audited = []

    def audit(tool, arguments, mutating=False):
        audited.append((tool, arguments, mutating))
        raise BridgeError("Dev audit append failed")

    monkeypatch.setattr(gate, "audit_dev_call", audit)
    with authorized_module_execution("revit_make_view"):
        with pytest.raises(BridgeError, match="audit append failed"):
            asyncio.run(provider._execute_approved_tool("revit_execute_python", {"script": "vetted", "mode": "write"}, "revit_make_view"))
    assert audited == [("revit_execute_python", {"script": "vetted", "mode": "write"}, True)]
    assert not revit.calls


def test_look_only_and_human_only_are_not_bypassed(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, mode="look_only")
    with pytest.raises(Exception, match="Look only"):
        asyncio.run(run_gated_tool(registry, gate, "revit_make_view", {"kind": "3d", "name": "Review", "tag": "DOC"}))
    with authorized_module_execution("revit_make_view"):
        with pytest.raises(Exception, match="Look only"):
            asyncio.run(provider._execute_approved_tool("revit_execute_python", {"mode": "write"}, "revit_make_view"))
        with pytest.raises(BridgeError, match="not available to AI"):
            asyncio.run(provider._execute_approved_tool("approve_plan", {}, "revit_make_view"))
        with pytest.raises(BridgeError, match="may only call"):
            asyncio.run(provider._execute_approved_tool("revit_set_parameter_value", {}, "revit_make_view"))
    assert not revit.calls


def test_auto_authorizes_outer_without_a_plan(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, mode="auto")
    result = asyncio.run(run_gated_tool(registry, gate, "revit_make_view", {"kind": "3d", "name": "Review", "tag": "DOC"}))
    assert result["ok"] is True
    assert len(revit.calls) == 1


def test_running_receipt_keeps_outer_claim_in_flight(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, raw={"status": "running", "request_id": RID})
    args = {"kind": "3d", "name": "Review", "tag": "DOC"}
    pid = approved(gate, "revit_make_view", args)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_make_view", {**args, "plan_id": pid}))
    assert result["status"] == "running" and result["verified"] is False
    action = gate.load_plan(pid)["actions"][0]
    assert action["state"] == "running" and action["in_flight_key"] == RID


def test_failed_transaction_is_not_booked_successful(tmp_path, monkeypatch):
    output = "SUMMARY\tfailed\nFAIL\tSTEP_FAILED\tRevit did not commit\nMETA\toutcome\trolled_back\nCOUNT\tfail\t1"
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, raw={"success": True, "output": output})
    args = {"kind": "3d", "name": "Review", "tag": "DOC"}
    pid = approved(gate, "revit_make_view", args)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_make_view", {**args, "plan_id": pid}))
    assert result["ok"] is False and result["changed_ids"] == []
    assert gate.load_plan(pid)["actions"][0]["state"] == "failed"


def test_fail_lines_cannot_be_turned_into_success():
    parsed = parse_script_output("SUMMARY\tx\nFAIL\tPOST\tfailed\nMETA\toutcome\tok\nCOUNT\tfail\t1")
    assert docs._finish_write("revit_make_view", parsed, 1, None)["ok"] is False


def test_read_module_does_not_get_an_approved_executor(tmp_path, monkeypatch):
    provider, gate, registry, revit, inst = wire(tmp_path, monkeypatch)
    seen = []

    def probe(approved_executor=None):
        seen.append(approved_executor)
        return {"ok": True}

    inst.class_instance.list_views_sheets_schedules = probe
    with authorized_module_execution("revit_list_views_sheets_schedules"):
        asyncio.run(provider.execute_tool("revit_list_views_sheets_schedules", {"approved_executor": lambda: None}))
    assert seen == [None]


def test_render_unknown_layout_is_partial_unverified(tmp_path, monkeypatch):
    path = tmp_path / "render.png"
    path.write_bytes(b"corrupt")
    monkeypatch.setattr(docs, "_server_in_mock_mode", lambda: False)
    result = docs.RevitDocsModule().render_check(view_id=1, output_path=str(path), workspace=WorkspaceMonitor([tmp_path]),
                                               tool_executor=lambda name, args: {"file_path": str(path)})
    assert result["verified"] is False
    assert result["limits"]["partial"] is True
    assert result["looks_blank"] is None
    assert any("NOT_ANALYSED" in info for info in result["info"])
