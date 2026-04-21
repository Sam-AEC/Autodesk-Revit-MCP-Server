# Logging And Audit

This repository records operational information in two different layers:

- Python-side audit logging
- C# bridge-side runtime logging

## Python Audit Recorder

The audit implementation lives in [packages/mcp-server-revit/src/revit_mcp_server/security/audit.py](../packages/mcp-server-revit/src/revit_mcp_server/security/audit.py).

`AuditRecorder.record()` writes one JSON line per tool invocation with:

- UTC timestamp
- tool name
- request ID
- payload
- response

This is the structured trail for MCP-level actions.

## Bridge Runtime Logs

The Revit add-in initializes Serilog in [App.cs](../packages/revit-bridge-addin/src/Bridge/App.cs).

Current behavior:

- log file path is created under `%APPDATA%\RevitMCP\Logs\bridge.jsonl`
- logs roll daily
- bridge startup, shutdown, request receipt, and execution errors are recorded

This is the operational trail for the .NET side of the system.

## Why Two Layers Exist

The Python process and the Revit add-in do not share a runtime or process boundary.

Because of that:

- Python audit logs tell you what the MCP layer believed it asked for
- bridge logs tell you what the Revit-hosted runtime actually received and executed

When debugging production issues, both logs matter.

## What To Expect In Incidents

If the MCP server validates and sends a request successfully, but Revit fails to execute it:

- Python audit may still look normal
- bridge log will often hold the actionable failure

If a path is rejected or payload shape is wrong before the bridge is contacted:

- Python audit and validation behavior will matter more than the bridge log

## Operational Rule

Never treat one log as the whole story. For live bridge failures, correlate:

1. Python audit entry
2. bridge runtime log entry
3. any client-visible error response

That three-point check is the fastest way to separate schema problems, transport problems, and live Revit execution problems.
