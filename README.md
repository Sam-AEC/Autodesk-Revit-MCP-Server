# Revit MCP Server

This repository is a rebuilt MCP server with a Revit-focused toolset. It includes a Python stdio server (`packages/mcp-server-revit`) with input validation, workspace enforcement, audit logging, and a mock bridge for CI, plus a .NET 4.8 Revit bridge add-in (`packages/revit-bridge-addin`) that exposes the same 25 tools via HTTP/ExternalEvent.

## Highlights
- 25 MCP tools covering health, audits, exports, sheet automation, QA, and reporting.
- Workspace sandboxing + JSON Schema validation + mock mode for tests.
- Revit bridge add-in with external event queue, HTTP listener, and placeholder implementations.
- Docs covering architecture, tools, installation, and troubleshooting.

See `docs/tools.md` for the full catalog and `history.txt` for the conversation log that inspired this rebuild.

## Demo client

The sample client in `packages/client-demo/demo.py` posts JSON payloads to the bridge server and prints the responses. Point it at `examples/revit-mcp-config.json` for bridge/mock URLs and run `python packages/client-demo/demo.py` to exercise `revit.health`, `revit.open_document`, and `revit.export_quantities`.

## Revit Bridge

The add-in runs a lightweight HTTP listener on `http://localhost:3000/` that accepts `{ "tool": "...", "payload": { ... } }` requests, then replies with stubbed JSON results through `BridgeCommandFactory`. Building and deploying the add-in places the manifest under `packages/revit-bridge-addin/RevitBridge.addin`.

## Running locally

Use `scripts/dev.ps1` to configure mock-mode environment variables and run the stdio server via `python -m revit_mcp_server`.
For a quick demo that posts to the bridge URL, run `scripts/run-demo.ps1` (the script sets up the workspace envs and launches the same Python entry point).
