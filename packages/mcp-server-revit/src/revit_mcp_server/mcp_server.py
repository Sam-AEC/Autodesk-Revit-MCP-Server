"""
MCP Server for AEC - Dynamic multi-provider automation server.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Tool, TextContent

from .errors import BridgeError
from .registry_factory import build_registry
from .security.approval import HUMAN_ONLY_TOOLS
from .security.dispatch import (
    gate_after, gate_after_result, gate_before, result_failed, settle_in_flight,
)
from .security.audit import redact_data
from .security.module_execution import authorized_module_execution
from .tool_metadata import enrich_tool

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = (
    "AEC Model Bridge exposes Autodesk Revit (and Navisworks, Rhino, IFC, Speckle) as MCP tools. "
    "Read-only tools run immediately. Every tool that changes a model requires an approved plan: "
    "call plan_actions with the proposed changes, then STOP and ask the person to review and approve the plan "
    "themselves, in the Revit panel's Plans view or with the command-line tool `aec-model-bridge-approve`. "
    "You cannot approve, reject or roll back a plan, and must not try to work around that. "
    "Only after the person tells you the plan is approved, call execute_plan (or pass the plan_id to the write tool "
    "with exactly the arguments that were approved; an approved action runs once). Revit lengths are in feet. "
    "In MCP_REVIT_MODE=mock the server returns canned responses and needs no Revit."
)


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("aec-model-bridge")
    except Exception:
        return "0.0.0"


def _make_server() -> Server:
    # Report this package's version (not the MCP SDK's) and, where the installed
    # SDK supports them, the usage instructions and website.
    wanted = {
        "version": _package_version(),
        "instructions": SERVER_INSTRUCTIONS,
        "website_url": "https://github.com/Sam-AEC/aec-model-bridge",
    }
    accepted = inspect.signature(Server.__init__).parameters
    return Server("aec-model-bridge", **{k: v for k, v in wanted.items() if k in accepted})


# Initialize the MCP server
app = _make_server()

# Registry components — populated in main() so importing this module never
# triggers provider construction (Rhino health probes, Speckle OAuth, SQLite
# connections, module filesystem scans) as a side effect.
registry = None
approval_provider = None
job_manager = None


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available AEC tools from registered providers."""
    # enrich_tool adds parameter docs and behaviour annotations (readOnlyHint,
    # destructiveHint, idempotentHint, openWorldHint) without changing behaviour.
    return [
        enrich_tool(provider.get_identity(), t)
        for provider in registry.get_all_providers()
        for t in provider.get_capabilities()
        if t.name not in HUMAN_ONLY_TOOLS
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent] | CallToolResult:
    """Execute a registered AEC tool."""
    if name in HUMAN_ONLY_TOOLS:
        return _tool_error("human_only", (
            f"Error: '{name}' is not available to AI clients. A person approves, rejects and rolls back "
            "plans in the Revit panel or with the aec-model-bridge-approve command. Ask them to do it."
        ))

    provider = registry.lookup_tool_provider(name)
    if not provider:
        return _tool_error("unknown_tool", f"Error: Unknown tool '{name}'")

    # Approval gate: a mutating call consumes its approved action here, before it
    # runs, so it can run at most once even if it fails or is called concurrently.
    gate = approval_provider.gate
    try:
        claim = gate_before(registry, gate, name, arguments)
    except Exception as e:
        return _tool_error("approval_blocked", f"Approval Gate Blocked: {str(e)}")

    try:
        # Check if deferred execution is requested.
        run_async = False
        idempotency_key = None
        if isinstance(arguments, dict):
            args_copy = dict(arguments)
            run_async = args_copy.pop("run_async", False)
            if isinstance(run_async, str):
                run_async = run_async.lower() in ("true", "1", "yes")
            run_async = bool(run_async)
            idempotency_key = args_copy.get("idempotency_key")

        if run_async:
            # The action was consumed above, when the job is queued; the job records
            # how it ended. A job that fails needs a new plan.
            async def run_tool_job(context=None):
                try:
                    with authorized_module_execution(name):
                        result = await provider.execute_tool(name, arguments)
                except BaseException as e:
                    gate_after(gate, claim, ok=False, error=str(e) or type(e).__name__)
                    raise
                # A 'running' answer keeps the claim consumed and the action in flight until
                # revit_get_result returns the final result; it is not booked as done here.
                outcome = gate_after_result(gate, claim, name, result)
                if outcome.state == "failed":
                    raise BridgeError(f"Tool returned failure: {json.dumps(redact_data(result))}")
                return result

            job_ref = await job_manager.submit(
                run_tool_job,
                idempotency_key=idempotency_key
            )
            response_text = f"✓ Job {job_ref.job_id} queued successfully\n\n"
            response_text += f"Result:\n{json.dumps(job_ref.to_dict(), indent=2)}"
            return [TextContent(type="text", text=response_text)]

        # Execute the tool on the provider
        try:
            with authorized_module_execution(name):
                result = await provider.execute_tool(name, arguments)
        except BaseException as e:
            gate_after(gate, claim, ok=False, error=str(e) or type(e).__name__)
            settle_in_flight(gate, name, arguments, error=e)
            raise
        if claim is None:
            settle_in_flight(gate, name, arguments, result=result)
        outcome = gate_after_result(gate, claim, name, result)
        failed = outcome.state == "failed" or _result_failed(result)

        redacted_result = redact_data(result)

        if outcome.state == "running":
            # Not an error and not done: Revit is still working and the approved action stays
            # consumed (it cannot be replayed) until revit_get_result brings the final result.
            kept = ("; the approved action stays used and cannot be run again" if claim else "")
            text = (
                f"{name} is still running. It has not finished and it has not failed{kept}. "
                f"Resume with {outcome.resume}. Do not repeat the call.\n\n"
                f"Result:\n{json.dumps(redacted_result, indent=2)}"
            )
            return [TextContent(type="text", text=text)]

        # Format the response
        response_text = f"{name} returned a failure\n\n" if failed else f"✓ {name} executed successfully\n\n"
        response_text += f"Result:\n{json.dumps(redacted_result, indent=2)}"

        if failed:
            return CallToolResult(
                isError=True, content=[TextContent(type="text", text=response_text)],
                structuredContent=redacted_result,
            )
        return [TextContent(type="text", text=response_text)]

    except BridgeError as e:
        return _tool_error("bridge_error", f"Revit Bridge Error: {str(e)}")

    except Exception as e:
        return _tool_error("execution_error", f"Error: {str(e)}")


_result_failed = result_failed


def _tool_error(kind: str, message: str) -> CallToolResult:
    """Preserve readable diagnostics while telling MCP clients the call failed."""
    message = redact_data(message)
    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=message)],
        structuredContent={"ok": False, "error": {"kind": kind, "message": message}},
    )

async def main():
    """Run the MCP server."""
    global registry, approval_provider, job_manager
    registry, approval_provider, job_manager, _module_registry, _workspace = build_registry()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    finally:
        await job_manager.shutdown(cancel_running=True)

def run_mcp_server():
    """Entry point for running the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    run_mcp_server()
