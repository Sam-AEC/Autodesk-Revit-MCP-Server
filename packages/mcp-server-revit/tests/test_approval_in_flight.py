"""A mutating call that comes back 'running' keeps its approval claim consumed and is closed only by the
final result from revit_get_result (or revit_job_status), even across a server restart."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult

from helpers import human_approve
from revit_mcp_server import mcp_server
from revit_mcp_server.errors import BridgeError, CommandFailed
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import (
    classify_outcome, gate_after_result, gate_before, run_gated_tool, settle_in_flight,
)

SET = "revit_set_parameter_value"
RID = "7b3c1d9e-0f6a-4c51-9d2a-5e8f1a2b3c4d"


def _args(i=1):
    return {"element_id": i, "parameter_name": "FireRating", "value": "60"}


def _approved(tmp_path, n=1):
    gate = ApprovalGate(tmp_path, "ask_first")
    plan = gate.create_plan([{"tool": SET, "arguments": _args(i)} for i in range(1, n + 1)], [{} for _ in range(n)])
    human_approve(gate, plan["plan_id"])
    return gate, plan["plan_id"]


class FakeRevit:
    """Provider whose write answers 'running' first; revit_get_result then answers from `outcomes`."""

    def __init__(self):
        self.calls = []
        self.write_result = {"status": "running", "state": "running", "request_id": RID}
        self.get_result = {"success": True, "changed": 1}  # or an exception to raise

    async def execute_tool(self, name, arguments):
        self.calls.append(name)
        if name == "revit_get_result":
            if isinstance(self.get_result, BaseException):
                raise self.get_result
            return self.get_result
        return self.write_result


def _wire(monkeypatch, gate, revit):
    registry = SimpleNamespace(
        lookup_tool_provider=lambda name: revit,
        lookup_tool=lambda name: SimpleNamespace(is_mutating=name == SET),
    )
    monkeypatch.setattr(mcp_server, "registry", registry)
    monkeypatch.setattr(mcp_server, "approval_provider", SimpleNamespace(gate=gate))
    return registry


def _call(name, arguments):
    return asyncio.run(mcp_server.call_tool(name, arguments))


def _action(gate, pid, index=0):
    return gate.load_plan(pid)["actions"][index]


def test_classify_outcome():
    assert classify_outcome(SET, {"status": "running", "request_id": RID}).state == "running"
    assert classify_outcome(SET, {"status": "running"}).state == "ok"  # no id to resume with: treat as data
    assert classify_outcome(SET, {"success": False, "error": "boom"}).error == "boom"
    assert classify_outcome(SET, {"ok": True}).state == "ok"
    assert classify_outcome("revit_run_job", {"job_id": "j1", "state": "queued"}).key == "job_j1"
    still = {"job_id": "j1", "state": "failed", "error": {"kind": "StillRunning", "request_id": RID, "message": "x"}}
    assert classify_outcome("revit_job_status", still).key == RID
    failed = {"job_id": "j1", "state": "failed", "error": {"kind": "ValueError", "message": "bad"}}
    assert classify_outcome("revit_run_job", failed).error == "bad"
    assert classify_outcome("revit_run_job", {"job_id": "j1", "state": "completed"}).state == "ok"


def test_running_result_keeps_the_claim_and_is_not_an_error(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    result = _call(SET, {**_args(), "plan_id": pid})
    assert not isinstance(result, CallToolResult), "still running is not an MCP error"
    text = result[0].text
    assert "still running" in text and f'revit_get_result(request_id="{RID}")' in text
    assert "executed successfully" not in text and "failure" not in text
    action = _action(gate, pid)
    assert action["state"] == "running" and action["in_flight_key"] == RID
    assert gate.load_plan(pid)["state"] == "approved"
    assert gate.in_flight(RID)["action_id"] == action["action_id"]


def test_replay_of_a_running_action_is_still_blocked(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    _call(SET, {**_args(), "plan_id": pid})
    again = _call(SET, {**_args(), "plan_id": pid})
    assert isinstance(again, CallToolResult) and again.isError
    assert again.structuredContent["error"]["kind"] == "approval_blocked"
    assert revit.calls == [SET], "the write must not reach Revit twice"


def test_get_result_done_closes_the_action_ok(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    _call(SET, {**_args(), "plan_id": pid})
    out = _call("revit_get_result", {"request_id": RID})
    assert "executed successfully" in out[0].text
    assert _action(gate, pid)["state"] == "executed"
    assert "in_flight_key" not in _action(gate, pid)
    assert gate.load_plan(pid)["state"] == "executed"
    assert gate.in_flight(RID) is None
    # a second collection does not touch anything
    _call("revit_get_result", {"request_id": RID})
    assert _action(gate, pid)["state"] == "executed"


def test_get_result_still_running_leaves_it_open(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    _call(SET, {**_args(), "plan_id": pid})
    revit.get_result = {"status": "running", "request_id": RID}
    _call("revit_get_result", {"request_id": RID})
    assert _action(gate, pid)["state"] == "running" and gate.in_flight(RID)


def test_get_result_failure_closes_the_action_not_ok_with_revits_message(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    _call(SET, {**_args(), "plan_id": pid})
    revit.get_result = CommandFailed("Bridge error: Wall is too short for the host\nStack: N/A")
    out = _call("revit_get_result", {"request_id": RID})
    assert isinstance(out, CallToolResult) and out.isError
    action = _action(gate, pid)
    assert action["state"] == "failed" and "Wall is too short" in action["error"]
    assert gate.load_plan(pid)["state"] == "partial"
    assert gate.in_flight(RID) is None


def test_a_failed_final_result_dict_also_closes_not_ok(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    _call(SET, {**_args(), "plan_id": pid})
    revit.get_result = {"success": False, "error": "script raised"}
    _call("revit_get_result", {"request_id": RID})
    action = _action(gate, pid)
    assert action["state"] == "failed" and "script raised" in action["error"]


@pytest.mark.parametrize("error", [
    BridgeError(f"Request {RID} is unknown to the add-in: its result expired or Revit was restarted."),
    BridgeError("Lost contact with the bridge while waiting for request x"),
])
def test_unknown_outcome_is_not_guessed(tmp_path, monkeypatch, error):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    _call(SET, {**_args(), "plan_id": pid})
    revit.get_result = error
    _call("revit_get_result", {"request_id": RID})
    assert _action(gate, pid)["state"] == "running" and gate.in_flight(RID), "left for a person to recover"


def test_in_flight_record_survives_a_server_restart(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    _call(SET, {**_args(), "plan_id": pid})
    del gate  # the server process ends

    restarted = ApprovalGate(tmp_path, "ask_first")
    assert [r["key"] for r in restarted.in_flight_records()] == [RID]
    with pytest.raises(BridgeError):  # still no replay after the restart
        gate_before(None_registry(), restarted, SET, {**_args(), "plan_id": pid})
    _wire(monkeypatch, restarted, revit)
    _call("revit_get_result", {"request_id": RID})
    assert _action(restarted, pid)["state"] == "executed"
    assert restarted.load_plan(pid)["state"] == "executed"


def None_registry():
    return SimpleNamespace(
        lookup_tool=lambda name: SimpleNamespace(is_mutating=True),
        lookup_tool_provider=lambda name: SimpleNamespace(),
    )


def test_only_the_first_settle_closes_and_a_person_s_abandon_wins(tmp_path):
    gate, pid = _approved(tmp_path)
    claim = gate_before(None_registry(), gate, SET, {**_args(), "plan_id": pid})
    gate_after_result(gate, claim, SET, {"status": "running", "request_id": RID})
    plan = gate.recover_running_actions(pid, "Revit crashed", force=True)
    assert plan["actions"][0]["state"] == "abandoned"
    assert gate.in_flight(RID) is None, "recovery drops the in-flight record"
    assert gate.settle_in_flight(RID, ok=True) is False
    assert _action(gate, pid)["state"] == "abandoned"


def test_settle_never_reopens_or_overwrites_a_closed_action(tmp_path):
    gate, pid = _approved(tmp_path)
    claim = gate_before(None_registry(), gate, SET, {**_args(), "plan_id": pid})
    gate_after_result(gate, claim, SET, {"status": "running", "request_id": RID})
    assert gate.settle_in_flight(RID, ok=False, error="first") is True
    assert gate.settle_in_flight(RID, ok=True) is False
    assert _action(gate, pid)["state"] == "failed"


def test_bad_request_ids_are_ignored(tmp_path):
    gate, _pid = _approved(tmp_path)
    assert gate.in_flight("../plans/evil") is None
    settle_in_flight(gate, "revit_get_result", {"request_id": "../x"}, result={"success": True})
    settle_in_flight(gate, "revit_get_result", {"request_id": 5}, result={"success": True})


def test_run_async_job_with_running_result_stays_in_flight(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)

    class Ref:
        job_id = "job-1"

        def to_dict(self):
            return {"job_id": "job-1", "status": "queued"}

    class Manager:
        async def submit(self, fn, idempotency_key=None):
            self.result = await fn(None)
            return Ref()

    manager = Manager()
    monkeypatch.setattr(mcp_server, "job_manager", manager)
    out = _call(SET, {**_args(), "plan_id": pid, "run_async": True})
    assert "queued" in out[0].text
    assert manager.result["status"] == "running"
    assert _action(gate, pid)["state"] == "running" and gate.in_flight(RID)
    _call("revit_get_result", {"request_id": RID})
    assert _action(gate, pid)["state"] == "executed"


def test_run_async_job_failure_still_closes_not_ok(tmp_path, monkeypatch):
    gate, pid = _approved(tmp_path)
    revit = FakeRevit()
    revit.write_result = {"success": False, "error": "nope"}
    _wire(monkeypatch, gate, revit)

    class Manager:
        async def submit(self, fn, idempotency_key=None):
            with pytest.raises(BridgeError):
                await fn(None)
            return SimpleNamespace(job_id="j", to_dict=lambda: {"job_id": "j"})

    monkeypatch.setattr(mcp_server, "job_manager", Manager())
    _call(SET, {**_args(), "plan_id": pid, "run_async": True})
    assert _action(gate, pid)["state"] == "failed"


def test_revit_run_job_report_is_followed_through_job_status(tmp_path):
    gate = ApprovalGate(tmp_path, "ask_first")
    job_args = {"command": "revit_set_parameter_value", "args": _args()}
    pid = gate.create_plan([{"tool": "revit_run_job", "arguments": job_args}], [{}])["plan_id"]
    human_approve(gate, pid)
    revit = FakeRevit()
    revit.write_result = {"job_id": "j9", "state": "running", "tool": SET, "progress": []}

    async def go():
        registry = SimpleNamespace(
            lookup_tool_provider=lambda name: revit,
            lookup_tool=lambda name: SimpleNamespace(is_mutating=name == "revit_run_job"),
        )
        await run_gated_tool(registry, gate, "revit_run_job", {**job_args, "plan_id": pid})
        assert _action(gate, pid)["state"] == "running" and gate.in_flight("job_j9")
        # Revit is still working on it after the job gave up waiting: re-keyed to the request id
        still = {"job_id": "j9", "state": "failed", "error": {"kind": "StillRunning", "request_id": RID, "message": "m"}}
        settle_in_flight(gate, "revit_job_status", {"job_id": "j9"}, result=still)
        assert gate.in_flight("job_j9") is None and gate.in_flight(RID)
        assert _action(gate, pid)["in_flight_key"] == RID
        settle_in_flight(gate, "revit_get_result", {"request_id": RID}, result={"success": True})
        assert _action(gate, pid)["state"] == "executed"

    asyncio.run(go())


def test_revit_run_job_failed_job_closes_not_ok(tmp_path):
    gate, pid = _approved(tmp_path)
    claim = gate_before(None_registry(), gate, SET, {**_args(), "plan_id": pid})
    outcome = gate_after_result(gate, claim, "revit_run_job", {"job_id": "j2", "state": "queued"})
    assert outcome.state == "running" and outcome.resume == 'revit_job_status(job_id="j2")'
    settle_in_flight(gate, "revit_job_status", {"job_id": "j2"},
                     result={"job_id": "j2", "state": "failed", "error": {"kind": "ValueError", "message": "bad arg"}})
    action = _action(gate, pid)
    assert action["state"] == "failed" and action["error"] == "bad arg"


def test_running_without_a_claim_just_reports(tmp_path, monkeypatch):
    gate = ApprovalGate(tmp_path, "auto")
    revit = FakeRevit()
    _wire(monkeypatch, gate, revit)
    out = json.dumps(_call(SET, _args())[0].text)
    assert "still running" in out and "stays used" not in out
    assert gate.in_flight_records() == []
