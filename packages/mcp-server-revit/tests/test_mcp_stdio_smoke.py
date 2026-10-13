"""End-to-end smoke test: spawn the real server over stdio and talk MCP to it.

This is the test that was missing when mcp 2.x was released: every other test
imports modules in-process, so a server that crashes while *starting* (or a wheel
that lacks its module data) went unnoticed. Here a fresh interpreter launches
``python -m revit_mcp_server.mcp_server`` exactly as an MCP client would.

The interpreter can be overridden with ``AEC_SMOKE_PYTHON`` so CI can run the very
same test against a wheel installed into a clean virtualenv.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

# A generous ceiling for the whole round trip: a warm run takes ~6-15 s, a cold
# Windows runner importing ifcopenshell/specklepy/anthropic for the first time ~40 s.
pytestmark = [pytest.mark.anyio, pytest.mark.timeout(120)]

MIN_TOOLS = 100


@pytest.fixture
def anyio_backend() -> str:
    # stdio_client spawns subprocesses with asyncio; trio is not exercised here.
    return "asyncio"


def _server_params(tmp_path: Path) -> StdioServerParameters:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("MCP_REVIT_")}
    env.update(
        {
            "MCP_REVIT_MODE": "mock",
            "MCP_REVIT_WORKSPACE_DIR": str(workspace),
            "MCP_REVIT_ALLOWED_DIRECTORIES": str(workspace),
            "MCP_REVIT_AUDIT_LOG": str(tmp_path / "audit.log"),
        }
    )
    # Never let a stray PYTHONPATH from the developer's shell mask a broken install
    # when a dedicated interpreter was requested.
    if os.environ.get("AEC_SMOKE_PYTHON"):
        env.pop("PYTHONPATH", None)
    return StdioServerParameters(
        command=os.environ.get("AEC_SMOKE_PYTHON", sys.executable),
        args=["-m", "revit_mcp_server.mcp_server"],
        env=env,
        cwd=str(tmp_path),
    )


async def test_server_boots_lists_tools_and_answers_health(tmp_path: Path) -> None:
    async with stdio_client(_server_params(tmp_path)) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.serverInfo.name == "aec-model-bridge"

            listed = await session.list_tools()
            tools = listed.tools
            assert len(tools) > MIN_TOOLS, f"only {len(tools)} tools listed"

            names = [t.name for t in tools]
            assert len(names) == len(set(names)), "duplicate tool names"
            # Module tools come from module.json files; they vanish when the
            # package data is missing from the installed wheel.
            assert "hello_world_say_hello" in names
            assert "module_list_commands" in names

            for tool in tools:
                assert tool.description and tool.description.strip(), tool.name
                assert tool.annotations is not None, f"{tool.name} has no annotations"
                assert tool.inputSchema.get("type") == "object", tool.name

            result = await session.call_tool("revit_health", {})
            assert not result.isError
            text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
            assert "revit_health executed successfully" in text
            payload = json.loads(text.split("Result:\n", 1)[1])
            assert payload["status"] == "healthy"

            # Error text alone used to be normalized by the SDK as isError=False.
            blocked = await session.call_tool("revit_execute_python", {"script": "print(doc.Title)"})
            assert blocked.isError
            assert blocked.structuredContent["error"]["kind"] == "approval_blocked"
            unknown = await session.call_tool("missing_villa_tool", {})
            assert unknown.isError
            assert unknown.structuredContent["error"]["kind"] == "unknown_tool"
    # Leaving both context managers must terminate the child without hanging;
    # reaching this line is the "closes cleanly" assertion.
