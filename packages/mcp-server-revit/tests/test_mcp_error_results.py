"""Tool failures must be observable as MCP failures, including redacted details."""
import asyncio
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult

from revit_mcp_server import mcp_server
from revit_mcp_server.errors import BridgeError, WorkspaceViolation
from revit_mcp_server.security.audit import redact_data


@pytest.mark.parametrize("error,kind", [
    (BridgeError("Parameter is not a shared parameter."), "bridge_error"),
    (WorkspaceViolation("outside allowed workspace"), "execution_error"),
    (ValueError("bad value token=private-example-token"), "execution_error"),
])
def test_failed_execution_reports_error_and_failed_plan_outcome(monkeypatch, error, kind):
    outcomes = []

    class Provider:
        async def execute_tool(self, name, arguments):
            raise error

    class Gate:
        def claim_action(self, name, arguments):
            return {"plan_id": "test-plan", "action_id": "test-action"}

        def finish_action(self, claim, ok, error=None):
            outcomes.append(ok)

    registry = SimpleNamespace(
        lookup_tool_provider=lambda name: Provider(),
        lookup_tool=lambda name: SimpleNamespace(is_mutating=True),
    )
    monkeypatch.setattr(mcp_server, "registry", registry)
    monkeypatch.setattr(mcp_server, "approval_provider", SimpleNamespace(gate=Gate()))
    result = asyncio.run(mcp_server.call_tool("test_write", {}))
    assert isinstance(result, CallToolResult)
    assert result.isError
    assert result.structuredContent["error"]["kind"] == kind
    assert outcomes == [False]
    assert "executed successfully" not in result.content[0].text
    assert "private-example-token" not in result.model_dump_json()
    if kind == "bridge_error":
        assert "Parameter is not a shared parameter" in result.content[0].text
        assert "localhost:3000" not in result.content[0].text


@pytest.mark.parametrize("name,kind", [
    ("approve_plan", "human_only"),
    ("missing_villa_tool", "unknown_tool"),
])
def test_non_executable_tools_report_mcp_errors(monkeypatch, name, kind):
    monkeypatch.setattr(mcp_server, "registry", SimpleNamespace(lookup_tool_provider=lambda name: None))
    result = asyncio.run(mcp_server.call_tool(name, {}))
    assert result.isError
    assert result.structuredContent["error"]["kind"] == kind


@pytest.mark.parametrize("payload", [
    {"success": False, "error": "missing element", "error_code": "ELEMENT_NOT_FOUND"},
    {"ok": False, "details": {"tested_elements": 2}},
    {"status": "error", "file_exists": False},
])
def test_explicit_provider_failures_preserve_data_and_fail_plan_outcome(monkeypatch, payload):
    outcomes = []

    class Provider:
        async def execute_tool(self, name, arguments):
            return payload

    class Gate:
        def claim_action(self, name, arguments):
            return {"plan_id": "test-plan", "action_id": "test-action"}

        def finish_action(self, claim, ok, error=None):
            outcomes.append(ok)

    monkeypatch.setattr(mcp_server, "registry", SimpleNamespace(
        lookup_tool_provider=lambda name: Provider(),
        lookup_tool=lambda name: SimpleNamespace(is_mutating=True),
    ))
    monkeypatch.setattr(mcp_server, "approval_provider", SimpleNamespace(gate=Gate()))
    result = asyncio.run(mcp_server.call_tool("test_write", {}))
    assert result.isError
    assert result.structuredContent == redact_data(payload)
    assert outcomes == [False]
    assert "executed successfully" not in result.content[0].text


@pytest.mark.parametrize("payload", [None, {}, {"status": "no_sheets"}, {"count": 0},
                                        {"value": False}, {"data": {"success": False}}])
def test_failure_detection_does_not_guess_from_normal_data(payload):
    assert not mcp_server._result_failed(payload)


def test_queued_provider_failure_marks_action_failed_and_raises_in_job(monkeypatch):
    outcomes, jobs = [], []

    class Provider:
        async def execute_tool(self, name, arguments):
            return {"success": False, "error": "fixture creation failed"}

    class Gate:
        def claim_action(self, name, arguments):
            return {"plan_id": "test-plan", "action_id": "test-action"}

        def finish_action(self, claim, ok, error=None):
            outcomes.append(ok)

    class JobManager:
        async def submit(self, fn, idempotency_key=None):
            jobs.append(fn)
            return SimpleNamespace(job_id="test-job", to_dict=lambda: {"job_id": "test-job"})

    monkeypatch.setattr(mcp_server, "registry", SimpleNamespace(
        lookup_tool_provider=lambda name: Provider(),
        lookup_tool=lambda name: SimpleNamespace(is_mutating=True),
    ))
    monkeypatch.setattr(mcp_server, "approval_provider", SimpleNamespace(gate=Gate()))
    monkeypatch.setattr(mcp_server, "job_manager", JobManager())

    async def run():
        queued = await mcp_server.call_tool("test_write", {"run_async": True})
        assert "queued successfully" in queued[0].text
        with pytest.raises(BridgeError, match="fixture creation failed"):
            await jobs[0]()

    asyncio.run(run())
    assert outcomes == [False]
