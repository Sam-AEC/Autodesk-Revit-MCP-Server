"""revit_run_job / revit_job_status / revit_job_cancel: async Revit work on top of JobManager."""
from __future__ import annotations

import asyncio
import threading

import pytest

from revit_mcp_server.config import BridgeMode
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.jobs import JobManager
from revit_mcp_server.providers.revit import RevitProvider
from revit_mcp_server.providers.revit_jobs import RevitJobProvider
from revit_mcp_server.registry_factory import build_registry
from revit_mcp_server.security.gating import requires_approval
from revit_mcp_server.security.workspace import WorkspaceMonitor


class GatedBridge:
    """Stands in for the add-in: every call blocks until the test releases it."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.release = {"first": threading.Event(), "second": threading.Event()}
        self.fail_with: str | None = None

    def send_tool(self, tool_name: str, payload: dict) -> dict:
        script = payload.get("script", "")
        self.started.append(script)
        if self.fail_with:
            raise BridgeError(self.fail_with)
        if script in self.release:
            self.release[script].wait(5)
        return {"success": True, "output": f"ran {script}", "progress": ["step 1", "step 2"]}


class DurableBridge:
    """Answers 'running' with a request_id, then yields the real result through get_result (like BridgeClient)."""

    def __init__(self, polls_until_done: int = 2) -> None:
        self.polls_until_done = polls_until_done
        self.polled: list[str] = []
        self.threads: set[int] = set()

    def send_tool(self, tool_name: str, payload: dict) -> dict:
        self.threads.add(threading.get_ident())
        return {"status": "running", "request_id": "req-1"}

    def get_result(self, request_id: str, wait_s: float | None = None) -> dict:
        self.threads.add(threading.get_ident())
        self.polled.append(request_id)
        if len(self.polled) < self.polls_until_done:
            return {"status": "running", "request_id": request_id}
        return {"success": True, "output": "slow result", "progress": ["half way"]}


def test_job_follows_a_running_answer_to_the_durable_result_off_the_event_loop(tmp_path):
    revit = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    bridge = DurableBridge()
    revit._bridge = bridge

    async def main():
        jobs = RevitJobProvider(revit, JobManager(), poll_s=0.01)
        result = await jobs.execute_tool("revit_run_job", {"script": "slow", "mode": "read", "wait_s": 5})
        assert result["state"] == "completed"
        assert result["output"]["output"] == "slow result"
        assert result["progress"] == ["half way"]
        return threading.get_ident()

    loop_thread = asyncio.run(main())
    assert bridge.polled == ["req-1", "req-1"]
    assert loop_thread not in bridge.threads  # send_tool and get_result ran on worker threads


def test_job_that_outlives_max_job_s_reports_the_request_id(tmp_path):
    revit = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    revit._bridge = DurableBridge(polls_until_done=10_000)

    async def main():
        jobs = RevitJobProvider(revit, JobManager(), poll_s=0.01, max_job_s=0.1)
        result = await jobs.execute_tool("revit_run_job", {"script": "slow", "mode": "read", "wait_s": 5})
        assert result["state"] == "failed"
        assert result["error"]["kind"] == "StillRunning"
        assert result["error"]["request_id"] == "req-1"
        assert "revit_get_result" in result["error"]["message"]

    asyncio.run(main())


@pytest.fixture
def parts(tmp_path):
    revit = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    bridge = GatedBridge()
    revit._bridge = bridge
    return revit, bridge


async def _until(provider, job_id, states, timeout=3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        status = await provider.execute_tool("revit_job_status", {"job_id": job_id})
        if status["state"] in states:
            return status
        assert asyncio.get_running_loop().time() < deadline, status
        await asyncio.sleep(0.02)


def test_run_job_returns_output_when_it_finishes_inside_the_wait(parts):
    revit, bridge = parts

    async def main():
        jobs = RevitJobProvider(revit, JobManager())
        result = await jobs.execute_tool(
            "revit_run_job", {"script": "quick", "mode": "read", "wait_s": 5}
        )
        assert result["state"] == "completed"
        assert result["output"]["output"] == "ran quick"
        assert result["progress"] == ["step 1", "step 2"]
        assert result["job_id"]
        status = await jobs.execute_tool("revit_job_status", {"job_id": result["job_id"]})
        assert status["state"] == "completed" and status["output"]["output"] == "ran quick"

    asyncio.run(main())
    assert bridge.started == ["quick"]


def test_slow_job_returns_a_job_id_then_completes(parts):
    revit, bridge = parts

    async def main():
        jobs = RevitJobProvider(revit, JobManager())
        started = await jobs.execute_tool("revit_run_job", {"script": "first", "mode": "read", "wait_s": 0})
        assert started["state"] in ("queued", "running")
        assert "output" not in started
        running = await _until(jobs, started["job_id"], {"running"})
        assert running["elapsed_s"] >= 0
        bridge.release["first"].set()
        done = await _until(jobs, started["job_id"], {"completed"})
        assert done["output"]["output"] == "ran first"

    asyncio.run(main())


def test_jobs_run_one_at_a_time_and_only_queued_jobs_cancel(parts):
    revit, bridge = parts

    async def main():
        jobs = RevitJobProvider(revit, JobManager())
        first = await jobs.execute_tool("revit_run_job", {"script": "first", "mode": "read", "wait_s": 0})
        await _until(jobs, first["job_id"], {"running"})
        second = await jobs.execute_tool("revit_run_job", {"script": "second", "mode": "read", "wait_s": 0})
        assert (await jobs.execute_tool("revit_job_status", {"job_id": second["job_id"]}))["state"] == "queued"
        assert bridge.started == ["first"]

        refused = await jobs.execute_tool("revit_job_cancel", {"job_id": first["job_id"]})
        assert refused["cancelled"] is False and refused["state"] == "running"
        assert "only queued" in refused["message"]

        cancelled = await jobs.execute_tool("revit_job_cancel", {"job_id": second["job_id"]})
        assert cancelled["cancelled"] is True and cancelled["state"] == "cancelled"

        bridge.release["first"].set()
        await _until(jobs, first["job_id"], {"completed"})
        again = await jobs.execute_tool("revit_job_cancel", {"job_id": first["job_id"]})
        assert again["cancelled"] is False and again["state"] == "completed"

    asyncio.run(main())
    assert bridge.started == ["first"]


def test_failed_call_reports_the_reason(parts):
    revit, bridge = parts
    bridge.fail_with = "Revit timed out"

    async def main():
        jobs = RevitJobProvider(revit, JobManager())
        result = await jobs.execute_tool("revit_run_job", {"script": "boom", "mode": "read", "wait_s": 5})
        assert result["state"] == "failed"
        assert "Revit timed out" in result["error"]["message"]

    asyncio.run(main())


def test_script_that_reports_failure_is_a_failed_job(parts):
    revit, bridge = parts
    bridge.send_tool = lambda tool, payload: {"success": False, "output": "", "error": "NameError: x"}

    async def main():
        jobs = RevitJobProvider(revit, JobManager())
        result = await jobs.execute_tool("revit_run_job", {"script": "bad", "mode": "read", "wait_s": 5})
        assert result["state"] == "failed"
        assert result["output"]["error"] == "NameError: x"

    asyncio.run(main())


def test_unknown_job_and_bad_arguments(parts):
    revit, _ = parts

    async def main():
        jobs = RevitJobProvider(revit, JobManager())
        with pytest.raises(ValueError):
            await jobs.execute_tool("revit_job_status", {"job_id": "nope"})
        with pytest.raises(ValueError):
            await jobs.execute_tool("revit_job_cancel", {"job_id": "nope"})
        for arguments in ({}, {"script": "a", "command": "revit_list_levels"}, {"command": "revit_not_a_tool"}):
            with pytest.raises(ValueError):
                await jobs.execute_tool("revit_run_job", arguments)

    asyncio.run(main())


# -- approval ----------------------------------------------------------------


@pytest.fixture
def stack(tmp_path):
    registry, approval, _jobs, _modules, _ws = build_registry(WorkspaceMonitor([tmp_path]))
    approval.gate.approval_mode = "required"
    return registry, approval


def _needs_gate(registry, arguments):
    tool = registry.lookup_tool("revit_run_job")
    return requires_approval(registry, "revit_run_job", tool, arguments)


def test_run_job_is_registered_gated_and_its_siblings_are_not(stack):
    registry, _ = stack
    assert registry.lookup_tool("revit_run_job").is_mutating is True
    assert registry.lookup_tool("revit_run_job").destructive is True
    assert registry.lookup_tool("revit_job_status").is_mutating is False
    assert registry.lookup_tool("revit_job_cancel").is_mutating is False


def test_read_only_jobs_skip_the_gate(stack):
    registry, _ = stack
    assert _needs_gate(registry, {"command": "revit_list_levels"}) is False
    assert _needs_gate(registry, {"command": "revit.list_levels"}) is False
    assert _needs_gate(registry, {"script": "print 1", "mode": "read"}) is False
    assert _needs_gate(registry, {"command": "revit_execute_python", "args": {"script": "print 1", "mode": "read"}}) is False


def test_mutating_jobs_keep_the_gate(stack):
    registry, approval = stack
    assert _needs_gate(registry, {"script": "print 1"}) is True
    assert _needs_gate(registry, {"script": "print 1", "mode": "write"}) is True
    assert _needs_gate(registry, {"command": "revit_create_wall", "args": {}}) is True
    assert _needs_gate(registry, {"command": "revit.create_wall"}) is True
    assert _needs_gate(registry, {"command": "revit_execute_python", "args": {"script": "print 1"}}) is True
    with pytest.raises(BridgeError):
        approval.gate.check_tool_execution("revit_run_job", {"script": "print 1"})


def test_read_mode_job_with_transaction_text_is_refused(stack):
    registry, _ = stack
    with pytest.raises(ValueError):
        _needs_gate(registry, {"script": "Transaction(doc, 'x')", "mode": "read"})
    with pytest.raises(ValueError):
        _needs_gate(registry, {"command": "revit_execute_python", "args": {"script": "Transaction(doc, 'x')", "mode": "read"}})


def test_job_end_to_end_in_mock_mode(stack):
    registry, _ = stack
    provider = registry.lookup_tool_provider("revit_run_job")

    async def main():
        result = await provider.execute_tool("revit_run_job", {"command": "revit_list_levels", "wait_s": 5})
        assert result["state"] == "completed"
        assert result["tool"] == "revit_list_levels"

    asyncio.run(main())
