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
from mcp.types import Tool, TextContent

from .errors import BridgeError
from .registry_factory import build_registry
from .security.audit import redact_data
from .tool_metadata import enrich_tool

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = (
    "AEC Model Bridge exposes Autodesk Revit (and Navisworks, Rhino, IFC, Speckle) as MCP tools. "
    "Read-only tools run immediately. Every tool that changes a model requires an approved plan: "
    "call plan_actions with the proposed changes, have the human approve it (approve_plan or the Revit panel), "
    "then call execute_plan or pass the plan_id to the write tool. Revit lengths are in feet. "
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
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Execute a registered AEC tool."""
    provider = registry.lookup_tool_provider(name)
    if not provider:
        return [TextContent(
            type="text",
            text=f"Error: Unknown tool '{name}'"
        )]

    # Approval Gate Middleware Check
    tool_def = registry.lookup_tool(name)
    if tool_def and tool_def.is_mutating:
        try:
            approval_provider.gate.check_tool_execution(name, arguments)
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Approval Gate Blocked: {str(e)}"
            )]

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
            async def run_tool_job(context=None):
                return await provider.execute_tool(name, arguments)

            job_ref = await job_manager.submit(
                run_tool_job,
                idempotency_key=idempotency_key
            )
            response_text = f"✓ Job {job_ref.job_id} queued successfully\n\n"
            response_text += f"Result:\n{json.dumps(job_ref.to_dict(), indent=2)}"
            return [TextContent(type="text", text=response_text)]

        # Execute the tool on the provider
        result = await provider.execute_tool(name, arguments)

        # If mutating tool and plan_id is provided, transition state to executed
        if tool_def and tool_def.is_mutating and isinstance(arguments, dict) and "plan_id" in arguments:
            plan_id = arguments["plan_id"]
            try:
                approval_provider.gate.update_plan_state(plan_id, "executed")
            except Exception:
                # The tool has already run, so don't fail the call and invite a
                # retry of a completed mutation; make the stale plan visible instead.
                logger.exception(
                    "Tool '%s' executed but plan '%s' could not be marked executed",
                    name,
                    plan_id,
                )

        redacted_result = redact_data(result)

        # Format the response
        response_text = f"✓ {name} executed successfully\n\n"
        response_text += f"Result:\n{json.dumps(redacted_result, indent=2)}"

        return [TextContent(type="text", text=response_text)]

    except BridgeError as e:
        error_msg = f"Revit Bridge Error: {redact_data(str(e))}\n\n"
        error_msg += "Make sure:\n"
        error_msg += "1. Revit is running\n"
        error_msg += "2. A project is open in Revit\n"
        error_msg += "3. The AEC Model Bridge add-in is loaded\n"
        error_msg += "4. The bridge is accessible at http://localhost:3000"

        return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error: {redact_data(str(e))}"
        )]

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
