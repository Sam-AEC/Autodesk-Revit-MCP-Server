"""The one gated way a model-reachable path runs a tool.

MCP calls, the panel's chat assistant, module tool executors (recipe steps) and the
panel's /execute route all go through here, so a new path cannot forget a check:

- approve_plan, reject_plan and rollback_plan are refused (a person runs them through
  ApprovalProvider.execute_human_tool);
- a mutating tool (unless the provider reports this call read-only, see gating.py) must consume an approved, unchanged plan action BEFORE it runs
  (ApprovalGate.claim_action); the action stays consumed if the tool fails.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..errors import BridgeError, CommandFailed
from .approval import HUMAN_ONLY_TOOLS, ApprovalGate
from .gating import requires_approval

logger = logging.getLogger(__name__)


GET_RESULT_TOOL = "revit_get_result"
JOB_STATUS_TOOL = "revit_job_status"
RUN_JOB_TOOL = "revit_run_job"
_JOB_TOOLS = frozenset({RUN_JOB_TOOL, JOB_STATUS_TOOL})


def refuse_human_only(name: str) -> None:
    if name in HUMAN_ONLY_TOOLS:
        raise BridgeError(
            f"'{name}' is not available to AI clients or automation. A person approves, rejects and rolls "
            "back plans in the Revit panel or with the aec-model-bridge-approve command."
        )


def gate_before(registry: Any, gate: Optional[ApprovalGate], name: str, arguments: Any
                ) -> Optional[Dict[str, str]]:
    """Refuse human-only tools and claim the approved action for a mutating tool."""
    refuse_human_only(name)
    tool_def = registry.lookup_tool(name) if registry is not None else None
    if gate is None or not (tool_def and tool_def.is_mutating):
        return None
    # A call that provably cannot change the model (revit_execute_python with mode='read',
    # or a revit_run_job wrapping one) skips the gate. A provider may raise to refuse it.
    if not requires_approval(registry, name, tool_def, arguments):
        return None
    return gate.claim_action(name, arguments)


def gate_after(gate: Optional[ApprovalGate], claim: Optional[Dict[str, str]], ok: bool,
               error: Optional[str] = None) -> None:
    """Record the outcome of a claimed action; never fails the call."""
    if gate is None or not claim:
        return
    try:
        gate.finish_action(claim, ok=ok, error=error)
    except Exception:
        logger.exception("Could not record the outcome of plan action %s", claim)


def result_failed(result: Any) -> bool:
    """Honor explicit provider failure signals without interpreting ordinary data."""
    return isinstance(result, dict) and (
        result.get("success") is False or result.get("ok") is False
        or result.get("status") in ("error", "failed", "failure")
    )


def job_key(job_id: Any) -> str:
    return "job_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(job_id))[:70]


@dataclass(frozen=True)
class Outcome:
    """How a provider result should be booked: state is 'ok', 'failed' or 'running'.

    For 'running', ``key`` ties the call to the approval claim (a Revit request id, or job_<id>)
    and ``resume`` says how to collect the final result."""
    state: str
    error: Optional[str] = None
    key: Optional[str] = None
    resume: Optional[str] = None


def _failure_text(result: Any) -> str:
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if error:
            return str(error)
        if result.get("message"):
            return str(result["message"])
    return "Tool returned an explicit failure"


def classify_outcome(tool: str, result: Any) -> Outcome:
    """Decide whether a provider result is final. A {"status": "running", "request_id": ...}
    answer (a call that outlived the wait while Revit keeps working) is NOT final: the action
    is neither done nor failed until revit_get_result returns the real result."""
    if isinstance(result, dict):
        request_id = result.get("request_id")
        if result.get("status") == "running" and isinstance(request_id, str) and request_id:
            return Outcome("running", key=request_id, resume=f'revit_get_result(request_id="{request_id}")')
        if tool in _JOB_TOOLS and result.get("job_id"):
            state = result.get("state")
            if state in ("queued", "running"):
                job_id = result["job_id"]
                return Outcome("running", key=job_key(job_id), resume=f'revit_job_status(job_id="{job_id}")')
            error = result.get("error")
            if state == "failed" and isinstance(error, dict) and error.get("kind") == "StillRunning"                     and isinstance(error.get("request_id"), str) and error["request_id"]:
                rid = error["request_id"]
                return Outcome("running", key=rid, resume=f'revit_get_result(request_id="{rid}")')
            if state in ("failed", "cancelled"):
                return Outcome("failed", error=_failure_text(result) if state == "failed" else "Job was cancelled")
    if result_failed(result):
        return Outcome("failed", error=_failure_text(result))
    return Outcome("ok")


def gate_after_result(gate: Optional[ApprovalGate], claim: Optional[Dict[str, str]], tool: str,
                      result: Any) -> Outcome:
    """Book the outcome of a claimed call. A 'running' result keeps the claim consumed (no
    replay) and records the action as in flight, on disk, until revit_get_result (or
    revit_job_status) brings the final result; it is never marked done or failed here."""
    outcome = classify_outcome(tool, result)
    if outcome.state == "running":
        if gate is not None and claim:
            try:
                gate.mark_in_flight(claim, outcome.key, tool)
            except Exception:
                logger.exception("Could not record plan action %s as in flight", claim)
        return outcome
    gate_after(gate, claim, ok=outcome.state == "ok", error=outcome.error)
    return outcome


def settle_in_flight(gate: Optional[ApprovalGate], tool: str, arguments: Any, result: Any = None,
                     error: Optional[BaseException] = None) -> None:
    """After revit_get_result / revit_job_status: close the in-flight action behind that id
    once Revit's final result is known. Never raises and never re-runs anything."""
    if gate is None or tool not in (GET_RESULT_TOOL, JOB_STATUS_TOOL) or not isinstance(arguments, dict):
        return
    try:
        if tool == GET_RESULT_TOOL:
            raw = arguments.get("request_id")
            key = raw.strip() if isinstance(raw, str) else None
        else:
            key = job_key(arguments.get("job_id")) if arguments.get("job_id") else None
        if not key or gate.in_flight(key) is None:
            return
        if error is not None:
            # Only Revit's own verdict closes the action; a lost connection or an expired
            # id leaves the outcome unknown and the action running for a person to recover.
            if isinstance(error, CommandFailed):
                gate.settle_in_flight(key, ok=False, error=str(error))
            return
        outcome = classify_outcome(JOB_STATUS_TOOL if tool == JOB_STATUS_TOOL else tool, result)
        if outcome.state == "running":
            if outcome.key and outcome.key != key:
                gate.rekey_in_flight(key, outcome.key)  # the job ended but Revit still runs it
            return
        gate.settle_in_flight(key, ok=outcome.state == "ok", error=outcome.error)
    except Exception:
        logger.exception("Could not settle the in-flight action for %s", tool)


async def run_gated_tool(registry: Any, gate: Optional[ApprovalGate], name: str, arguments: Any,
                         not_found: str = "Unknown tool '{name}'") -> Any:
    refuse_human_only(name)
    provider = registry.lookup_tool_provider(name) if registry is not None else None
    if not provider:
        raise ValueError(not_found.format(name=name))
    claim = gate_before(registry, gate, name, arguments)
    try:
        result = await provider.execute_tool(name, arguments)
    except BaseException as e:
        gate_after(gate, claim, ok=False, error=str(e) or type(e).__name__)
        settle_in_flight(gate, name, arguments, error=e)
        raise
    if claim is None:
        settle_in_flight(gate, name, arguments, result=result)
        return result
    gate_after_result(gate, claim, name, result)
    return result
