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
from typing import Any, Dict, Optional

from ..errors import BridgeError
from .approval import HUMAN_ONLY_TOOLS, ApprovalGate
from .gating import requires_approval

logger = logging.getLogger(__name__)


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
        raise
    gate_after(gate, claim, ok=True)
    return result
