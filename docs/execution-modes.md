# Execution Modes

The server supports two runtime modes, defined by `BridgeMode` in [config.py](../packages/mcp-server-revit/src/revit_mcp_server/config.py).

## `mock` Mode

`mock` is the default mode.

Behavior:

- the Python MCP process stays fully functional
- tool requests are handled without a live Revit process
- bridge traffic is replaced by deterministic mock responses
- workspace and audit behavior still run

Why it exists:

- local development without Revit
- CI validation on machines that do not have Autodesk Revit installed
- regression tests that need stable outputs

## `bridge` Mode

`bridge` mode forwards tool calls to the local Revit add-in over HTTP.

Behavior:

- the Python server validates input and routes calls
- the bridge client sends requests to `MCP_REVIT_BRIDGE_URL`
- the C# add-in queues work onto Revit's UI thread through `ExternalEvent`
- responses flow back through the Python layer to the MCP client

Requirements:

- Windows
- installed Revit bridge add-in
- running Revit session
- reachable localhost bridge endpoint

## Why The Split Matters

This repo uses one codebase for two very different environments:

- deterministic test and automation environments
- real Revit automation environments with UI-thread constraints

That is why the Python package contains both:

- `bridge/mock.py`
- `bridge/client.py`

The MCP-facing interface stays stable while the execution backend changes underneath it.

## Operational Guidance

Use `mock` when you need repeatable validation or when Revit is unavailable. Use `bridge` only when the add-in is installed and the target workflow genuinely needs live Revit API execution.
