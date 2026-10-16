"""Owns a native (non-CLI) chat loop against the Anthropic API directly.

Sibling to agent_bridge.py, not a replacement for it: agent_bridge.py shells
out to an already-installed, already-authenticated `claude`/`codex` CLI so
the panel gets a real chat surface without this hub owning an LLM agent
loop. This module is the opposite bet - it owns the model call and the
tool-calling loop directly against the Anthropic API using only an API key,
because the CLI-shelling path fails out of the box on a fresh install with
neither CLI on PATH (see docs/0012-native-agent-chat-backend.md for the
decision record). Both modules keep the exact same safety boundary: a
mutating Revit tool call must pass ApprovalGate.check_tool_execution before
it runs, no matter which chat surface requested it - this module is not
exempt, and must never grow a bypass, debug flag, or "trusted mode" for it.

Tool calls are dispatched through the same ProviderRegistry every other
caller in this codebase uses (mcp_server.py's stdio server, panel_server.py's
HTTP shim): `registry.get_all_tools()` already carries the exact
name/description/input_schema shape Anthropic's tool-use API wants, so no
schema translation is needed to build the `tools=[...]` request parameter.

Session state is in-memory only - a module-level dict keyed by session_id
holding the running message list. Conversations are lost on hub restart;
that is an accepted v1 limitation. Persistence is explicitly out of scope.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from .config import config
from .security.approval import HUMAN_ONLY_TOOLS
from .security.dispatch import run_gated_tool

logger = logging.getLogger(__name__)

# Anthropic's current flagship model as of this writing. This loop drives
# real decisions about which Revit tools to call (including which mutating
# actions to propose) - correctness matters more than raw throughput here,
# so this is not a route worth downgrading to a cheaper/faster tier.
_MODEL_ID = "claude-opus-5"

# Non-streaming request; 16000 leaves generous headroom for a full reply
# (including tool-call planning) comfortably under the SDK's HTTP timeout
# without needing to switch to streaming for this feature.
_MAX_TOKENS = 16000

# Hard cap on model turns (i.e. calls to messages.create) per
# run_native_turn() invocation, so a model stuck requesting tool calls can
# never loop forever.
_MAX_TURNS = 10

_TURN_CAP_ERROR = (
    "Conversation exceeded the maximum number of tool-calling turns (10) "
    "without a final response."
)

_MISSING_KEY_ERROR = (
    "No Anthropic API key configured. Set the MCP_REVIT_ANTHROPIC_API_KEY "
    "environment variable and restart Revit."
)

_SYSTEM_PROMPT = (
    "You are the AI assistant embedded in the AEC Model Bridge Revit panel. "
    "You can call the provided tools to inspect and modify the open Revit "
    "model. Mutating tools require an approved plan: call plan_actions to "
    "propose one; a human then reviews and approves it in the panel's Plans "
    "view - you cannot approve your own plans. Once a plan is approved, call "
    "execute_plan to run it. If a mutating call is rejected because no "
    "approved plan backs it, tell the user to review the plan in the panel "
    "rather than retrying blindly. If any tool call returns an error, explain "
    "the failure to the user."
)

# Plan-lifecycle tools the model must never be able to call. The approval
# workflow's entire guarantee is that a HUMAN moves a plan to "approved":
# execute_plan only checks the plan's state flag, and approve_plan is what
# sets that flag, with no gate of its own (none of these are is_mutating).
# If the model could call approve_plan it could propose, approve and execute
# its own plan with no human involved. Approve/reject happen only through
# the panel's Plans view (BridgePanel's plan.approve / plan.reject relay,
# which calls the hub's /execute endpoint directly, outside this loop).
# rollback_plan is excluded for the same reason: it writes to the model
# without any plan approval of its own.
_MODEL_EXCLUDED_TOOLS = HUMAN_ONLY_TOOLS

# session_id -> running message list (user/assistant/tool_result turns so
# far). In-memory only - see module docstring.
_sessions: Dict[str, List[Dict[str, Any]]] = {}


def _build_tools(registry) -> List[Dict[str, Any]]:
    """Builds the Anthropic `tools=[...]` parameter directly from the
    registry's ProviderTool objects - .input_schema is already valid JSON
    Schema, no translation needed. Tools in _MODEL_EXCLUDED_TOOLS are never
    offered to the model (see that constant for why).

    The last tool carries an ephemeral cache_control breakpoint: the full
    tool list is large (~280 tools, tens of KB of schema) and identical on
    every one of up to _MAX_TURNS model calls per turn, so caching the tools
    prefix avoids re-processing it uncached on each call."""
    tools: List[Dict[str, Any]] = [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        for tool in registry.get_all_tools()
        if tool.name not in _MODEL_EXCLUDED_TOOLS
    ]
    if tools:
        tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools


async def _execute_tool_call(registry, approval_provider, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executes one tool call, gated exactly like panel_server.py's
    _run_tool_sync: mutating tools must pass ApprovalGate.check_tool_execution
    before they run. This is the safety boundary every tool-calling path in
    this codebase shares - do not skip it and do not add a bypass."""
    # Defense in depth: _build_tools never offers these, but refuse them here
    # too in case the model emits a tool_use for a name it was not given.
    if name in _MODEL_EXCLUDED_TOOLS:
        raise PermissionError(
            f"Tool '{name}' is not available to the chat assistant; plans are "
            "approved, rejected and rolled back by a human in the panel's Plans view."
        )

    # Shared gated dispatch: refuses human-only tools and consumes the approved
    # action before a mutating tool runs (at most once, even if it fails).
    return await run_gated_tool(registry, approval_provider.gate, name, arguments)


async def _execute_tool_calls(
    registry, approval_provider, tool_use_blocks: List[Any]
) -> List[Tuple[str, Dict[str, Any], bool]]:
    """Runs every tool_use block requested in one model turn, sequentially.

    Returns (tool_use_id, result, is_error) per block. A failing tool call
    (approval-gate rejection, unknown tool, Revit-side error, ...) does NOT
    raise: it becomes an {"error": ...} result with is_error=True, so the
    model sees the failure and can explain it, and any earlier call in the
    same turn that already succeeded (possibly a mutation) stays recorded in
    session history instead of being rolled back and later re-applied.

    Sequential (not asyncio.gather) is deliberate: ApprovalGate reads and
    writes plan state as plain JSON files on disk, so mutating tool calls
    within the same turn must not race each other against that state.
    """
    results: List[Tuple[str, Dict[str, Any], bool]] = []
    for block in tool_use_blocks:
        try:
            result = await _execute_tool_call(registry, approval_provider, block.name, block.input)
            results.append((block.id, result, False))
        except Exception as e:
            logger.info("Native chat tool call '%s' failed: %s", block.name, e)
            results.append((block.id, {"error": str(e)}, True))
    return results


def _extract_text(content: List[Any]) -> str:
    return "".join(getattr(block, "text", "") for block in content if getattr(block, "type", None) == "text")


def _extract_tool_uses(content: List[Any]) -> List[Any]:
    return [block for block in content if getattr(block, "type", None) == "tool_use"]


def run_native_turn(
    message: str,
    session_id: Optional[str],
    registry,
    approval_provider,
) -> Dict[str, Any]:
    """Runs one chat turn against the Anthropic API directly, driving
    Claude's own tool-calling loop against this hub's ProviderRegistry.

    Returns {"ok": True, "response": str, "session_id": str} on success, or
    {"ok": False, "error": str} - never raises for expected failure modes
    (missing API key, Anthropic API error, hitting the turn cap) so a later
    HTTP layer can pass this straight through as the response body, exactly
    like agent_bridge.run_agent_turn already does today. An individual tool
    call failing is NOT a turn failure: it is returned to the model as an
    is_error tool_result and the conversation continues.

    Sync by design: this matches agent_bridge.run_agent_turn's signature,
    which is what the HTTP layer (panel_server.py, a synchronous
    BaseHTTPRequestHandler) calls directly today. The Anthropic client calls
    are themselves synchronous (client.messages.create, no I/O-bound
    concurrency needed for a single chat turn); only tool execution
    (AECProvider.execute_tool) is async, so each model turn that requests
    tool calls opens one asyncio.run() to execute them - mirroring
    panel_server.py's _run_tool_sync bridge, but batched per turn (not per
    individual tool call and not for the whole multi-turn conversation) so a
    turn with several tool calls doesn't spin up a fresh event loop per
    call.
    """
    if not config.anthropic_api_key:
        return {"ok": False, "error": _MISSING_KEY_ERROR}

    if session_id and session_id in _sessions:
        resolved_session_id = session_id
    else:
        resolved_session_id = str(uuid.uuid4())
        _sessions[resolved_session_id] = []

    history = _sessions[resolved_session_id]
    snapshot_len = len(history)

    try:
        history.append({"role": "user", "content": message})

        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        tools = _build_tools(registry)

        for _ in range(_MAX_TURNS):
            response = client.messages.create(
                model=_MODEL_ID,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=history,
                tools=tools,
            )

            # Append the full content block list (not just extracted text) -
            # this preserves tool_use/thinking blocks exactly as the model
            # produced them, which the API requires when continuing a
            # conversation that included tool calls.
            history.append({"role": "assistant", "content": response.content})

            tool_use_blocks = _extract_tool_uses(response.content)
            if not tool_use_blocks:
                return {"ok": True, "response": _extract_text(response.content), "session_id": resolved_session_id}

            executed = asyncio.run(_execute_tool_calls(registry, approval_provider, tool_use_blocks))
            tool_result_blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result, default=str),
                    **({"is_error": True} if is_error else {}),
                }
                for tool_use_id, result, is_error in executed
            ]
            history.append({"role": "user", "content": tool_result_blocks})

        return {"ok": False, "error": _TURN_CAP_ERROR}
    except Exception as e:
        # Reserved for genuine transport/API-level failures (e.g. a network
        # error or 4xx/5xx from client.messages.create) - per-tool-call
        # failures never reach here, they become is_error tool_results in
        # _execute_tool_calls. Roll back everything this call added to the
        # session: a failure partway through could otherwise leave a
        # dangling tool_use block in history with no matching tool_result,
        # which the Anthropic API rejects with a 400 on every subsequent
        # turn, permanently breaking this session_id. Rolling back leaves
        # the session exactly as it was before this failed call, so a retry
        # (or a different message) still works.
        del history[snapshot_len:]
        logger.warning("Native chat turn failed: %s", e)
        return {"ok": False, "error": str(e)}
