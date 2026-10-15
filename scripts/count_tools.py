#!/usr/bin/env python
"""Print how many tools AEC Model Bridge has. This is the one definition of the count.

A tool is one entry in the tools/list reply of the stdio MCP server in its
default setup:

- the registry that registry_factory.build_registry() builds (all providers and
  the module tools), listed the way mcp_server.list_tools() lists it;
- no Autodesk Data credentials (so no Autodesk Data tools), no
  MCP_PROXY_TARGETS (so no proxied tools), user modules off;
- the human-only approval tools (approve_plan, reject_plan, rollback_plan) are
  not listed to AI clients, so they are not counted.

Mock and bridge mode list the same tools. Add-in commands (the [BridgeCommand]
methods in the Revit add-in, reached through revit_raw_command) are not tools;
they are printed separately as "addin_commands".

Usage:  python scripts/count_tools.py [--json]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "packages" / "mcp-server-revit" / "src"
ADDIN_SRC = ROOT / "packages" / "revit-bridge-addin" / "src"

# Settings that change what the server lists. Cleared so the count is the default setup.
_SCRUB_PREFIXES = ("APS_", "SPECKLE_", "MCP_PROXY_", "MCP_REVIT_")


def count_addin_commands() -> int:
    names: set[str] = set()
    pattern = re.compile(r'\[BridgeCommand\(\s*"([^"]+)"')
    for path in ADDIN_SRC.rglob("*.cs"):
        names.update(pattern.findall(path.read_text(encoding="utf-8", errors="replace")))
    return len(names)


def count_tools() -> dict:
    for key in [k for k in os.environ if k.startswith(_SCRUB_PREFIXES)]:
        del os.environ[key]
    workspace_dir = tempfile.mkdtemp(prefix="count-tools-")
    os.environ["MCP_REVIT_MODE"] = "mock"
    os.environ["MCP_REVIT_WORKSPACE_DIR"] = workspace_dir
    os.environ["MCP_REVIT_ALLOWED_DIRECTORIES"] = workspace_dir
    sys.path.insert(0, str(SRC))

    from revit_mcp_server import mcp_server
    from revit_mcp_server.registry_factory import build_registry
    from revit_mcp_server.security.approval import HUMAN_ONLY_TOOLS
    from revit_mcp_server.security.workspace import WorkspaceMonitor

    registry, approval, job_manager, _modules, _ws = build_registry(WorkspaceMonitor([Path(workspace_dir)]))
    mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = registry, approval, job_manager
    listed = asyncio.run(mcp_server.list_tools())

    by_provider: collections.Counter[str] = collections.Counter()
    registered = 0
    for provider in registry.get_all_providers():
        for tool in provider.get_capabilities():
            registered += 1
            if tool.name not in HUMAN_ONLY_TOOLS:
                by_provider[provider.get_identity()] += 1

    assert sum(by_provider.values()) == len(listed), "provider tally and tools/list disagree"
    return {
        "tools": len(listed),
        "by_provider": dict(sorted(by_provider.items())),
        "human_only_not_listed": sorted(HUMAN_ONLY_TOOLS),
        "registered_including_human_only": registered,
        "addin_commands": count_addin_commands(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    args = parser.parse_args()
    result = count_tools()
    if args.json:
        print(json.dumps(result))
        return 0
    print(f"tools: {result['tools']}  (entries in tools/list, default setup)")
    for name, n in result["by_provider"].items():
        print(f"  {name}: {n}")
    print(f"human-only, not listed: {', '.join(result['human_only_not_listed'])}")
    print(f"addin_commands: {result['addin_commands']}  (not tools; reached through revit_raw_command)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
