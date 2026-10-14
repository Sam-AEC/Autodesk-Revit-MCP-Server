"""Integration tests for ApprovalProvider: plan_actions -> approve -> execute_plan ->
rollback_plan, wired through a real ProviderRegistry against a fake in-memory parameter
store. These exercise the full round trip that providers/approval_provider.py promises,
not just the ApprovalGate state machine in isolation (see test_approval_gate.py).
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from revit_mcp_server.providers.approval_provider import ApprovalProvider
from revit_mcp_server.providers.base import AECProvider, ProviderTool
from revit_mcp_server.providers.registry import ProviderRegistry
from revit_mcp_server.security.workspace import WorkspaceMonitor
from helpers import panel_decide


class FakeParamStore(AECProvider):
    """Minimal stand-in for RevitProvider's parameter tools, backed by a plain dict."""

    def __init__(self, values: Dict[int, Dict[str, Any]]):
        self.values = values
        self.fail_on = set()  # set of element_id to force execute_tool failures for

    def get_identity(self) -> str:
        return "fake_revit"

    def get_capabilities(self) -> List[ProviderTool]:
        return [
            ProviderTool(
                name="revit_get_parameter_value",
                description="test",
                inputSchema={"type": "object", "properties": {}},
            ),
            ProviderTool(
                name="revit_set_parameter_value",
                description="test",
                inputSchema={"type": "object", "properties": {}},
                is_mutating=True,
            ),
        ]

    async def check_health(self) -> Dict[str, Any]:
        return {"status": "healthy"}

    async def shutdown(self) -> None:
        pass

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        elem_id = arguments.get("element_id")
        param_name = arguments.get("parameter_name")
        if name == "revit_get_parameter_value":
            return {"value": self.values.get(elem_id, {}).get(param_name)}
        if name == "revit_set_parameter_value":
            if elem_id in self.fail_on:
                raise RuntimeError(f"simulated failure writing element {elem_id}")
            self.values.setdefault(elem_id, {})[param_name] = arguments.get("value")
            return {"status": "success"}
        raise ValueError(f"unknown tool {name}")


@pytest.fixture
def registry_and_provider(tmp_path):
    registry = ProviderRegistry()
    workspace = WorkspaceMonitor([tmp_path])
    approval = ApprovalProvider(workspace=workspace, registry=registry, approval_mode="required")
    registry.register(approval)
    store = FakeParamStore({1: {"FireRating": "30"}, 2: {"FireRating": "45"}})
    registry.register(store)
    return registry, approval, store


@pytest.mark.anyio
async def test_plan_actions_captures_before_state_from_live_provider(registry_and_provider):
    registry, approval, store = registry_and_provider
    plan = await approval.execute_tool("plan_actions", {
        "actions": [
            {"tool": "revit_set_parameter_value", "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"}},
        ]
    })
    assert plan["state"] == "pending"
    assert plan["actions"][0]["diff"]["before"] == {"1": {"FireRating": "30"}}


@pytest.mark.anyio
async def test_execute_plan_applies_all_actions_and_marks_executed(registry_and_provider):
    registry, approval, store = registry_and_provider
    plan = await approval.execute_tool("plan_actions", {
        "actions": [
            {"tool": "revit_set_parameter_value", "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"}},
            {"tool": "revit_set_parameter_value", "arguments": {"element_id": 2, "parameter_name": "FireRating", "value": "60"}},
        ]
    })
    plan_id = plan["plan_id"]
    await panel_decide(approval, "approve_plan", plan_id)

    result = await approval.execute_tool("execute_plan", {"plan_id": plan_id})
    assert result["state"] == "executed"
    assert store.values[1]["FireRating"] == "60"
    assert store.values[2]["FireRating"] == "60"


@pytest.mark.anyio
async def test_execute_plan_rejects_unapproved(registry_and_provider):
    registry, approval, store = registry_and_provider
    plan = await approval.execute_tool("plan_actions", {
        "actions": [{"tool": "revit_set_parameter_value", "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"}}]
    })
    with pytest.raises(ValueError, match="not 'approved'"):
        await approval.execute_tool("execute_plan", {"plan_id": plan["plan_id"]})


@pytest.mark.anyio
async def test_execute_plan_partial_failure_reports_and_continues(registry_and_provider):
    """One action failing must not silently swallow the rest, and must not mark
    the plan fully 'executed' — both successes and failures are recorded."""
    registry, approval, store = registry_and_provider
    store.fail_on.add(2)

    plan = await approval.execute_tool("plan_actions", {
        "actions": [
            {"tool": "revit_set_parameter_value", "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"}},
            {"tool": "revit_set_parameter_value", "arguments": {"element_id": 2, "parameter_name": "FireRating", "value": "60"}},
        ]
    })
    plan_id = plan["plan_id"]
    await panel_decide(approval, "approve_plan", plan_id)
    result = await approval.execute_tool("execute_plan", {"plan_id": plan_id})

    assert result["state"] == "partial"  # mixed result — not fully executed, not fully failed
    assert store.values[1]["FireRating"] == "60"  # succeeded action applied
    assert store.values[2]["FireRating"] == "45"  # failed action left untouched
    errors = [r for r in result["results"] if "error" in r]
    assert len(errors) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("answer", [
    {"success": False, "error": "Revit rolled back the placement"},
    {"ok": False, "message": "Post-check failed"},
])
async def test_execute_plan_records_provider_failure_without_exception(registry_and_provider, monkeypatch, answer):
    _, approval, store = registry_and_provider
    plan = await approval.execute_tool("plan_actions", {"actions": [
        {"tool": "revit_set_parameter_value", "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"}},
    ]})
    await panel_decide(approval, "approve_plan", plan["plan_id"])

    async def refused(name, arguments):
        return answer

    monkeypatch.setattr(store, "execute_tool", refused)
    result = await approval.execute_tool("execute_plan", {"plan_id": plan["plan_id"]})
    assert result["ok"] is False and result["state"] == "partial"
    saved = approval.gate.load_plan(plan["plan_id"])
    assert saved["actions"][0]["state"] == "failed"
    assert result["results"][0]["error"] == answer.get("error", answer.get("message"))
    assert store.values[1]["FireRating"] == "30"


@pytest.mark.anyio
async def test_execute_plan_keeps_running_receipt_consumed_and_has_no_success_proof(registry_and_provider, monkeypatch):
    from revit_mcp_server.security.dispatch import classify_outcome

    _, approval, store = registry_and_provider
    plan = await approval.execute_tool("plan_actions", {"actions": [
        {"tool": "revit_set_parameter_value", "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"}},
    ]})
    await panel_decide(approval, "approve_plan", plan["plan_id"])
    calls = []

    async def running(name, arguments):
        calls.append(name)
        return {"status": "running", "request_id": "req-plan-pending"}

    monkeypatch.setattr(store, "execute_tool", running)
    result = await approval.execute_tool("execute_plan", {"plan_id": plan["plan_id"]})
    assert classify_outcome("execute_plan", result).state == "running"
    assert result["pending_results"][0]["resume"] == 'revit_get_result(request_id="req-plan-pending")'
    saved = approval.gate.load_plan(plan["plan_id"])
    assert saved["actions"][0]["state"] == "running"
    assert approval.gate.in_flight("req-plan-pending")
    assert "executed_at" not in saved
    assert approval.gate.load_proof(plan["plan_id"]) is None
    repeated = await approval.execute_tool("execute_plan", {"plan_id": plan["plan_id"]})
    assert classify_outcome("execute_plan", repeated).state == "running"
    assert approval.gate.load_proof(plan["plan_id"]) is None
    assert calls == ["revit_set_parameter_value"]


@pytest.mark.anyio
async def test_full_roundtrip_plan_approve_execute_rollback(registry_and_provider):
    registry, approval, store = registry_and_provider
    plan = await approval.execute_tool("plan_actions", {
        "actions": [{"tool": "revit_set_parameter_value", "arguments": {"element_id": 1, "parameter_name": "FireRating", "value": "60"}}]
    })
    plan_id = plan["plan_id"]
    await panel_decide(approval, "approve_plan", plan_id)
    await approval.execute_tool("execute_plan", {"plan_id": plan_id})
    assert store.values[1]["FireRating"] == "60"

    rolled_back = await panel_decide(approval, "rollback_plan", plan_id)
    assert rolled_back["state"] == "rolled_back"
    assert store.values[1]["FireRating"] == "30"
