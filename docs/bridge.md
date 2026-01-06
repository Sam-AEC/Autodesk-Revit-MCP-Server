# Revit Bridge Architecture

This document explains how the MCP server interacts with the Revit bridge add-in.

## HTTP Bridge

- The add-in starts `BridgeServer`, which listens on `http://localhost:3000/` for JSON POSTs matching `{"tool": "<name>", "payload": {...}}`.
- Incoming requests are routed through `BridgeCommandFactory.Execute`, which currently returns deterministic mock data keyed by the 25 tool names (health, exports, QA, sheets, etc.).
- Responses are written back to the MCP server, which can run in either mock mode or `bridge` mode (`MCP_REVIT_MODE=bridge`).

## ExternalEvent Execution

- An `ExternalEventHandler` is registered alongside the HTTP listener. It is meant to queue tool execution tasks on the Revit UI thread to satisfy API constraints.
- Future work can push real command requests into that queue, allowing C# handlers to open documents, export schedules, run QA, and export sheets.

## Building & Deployment

1. Set `REVIT_SDK` to the installed Revit SDK root.
2. Run `scripts/build-addin.ps1` to compile `packages/revit-bridge-addin/RevitBridge.csproj`.
3. Use `scripts/install-addin.ps1 -RevitYear <year>` to drop `RevitBridge.addin` under `%ProgramData%\Autodesk\Revit\Addins\<year>`.
4. Launch Revit to load the add-in and keep the HTTP listener running on startup.

## Extending the Toolset

- Add new stub implementations to `BridgeCommandFactory.Execute` for each MCP tool required by the server.
- Mirror the same tool names and schemas defined in `packages/mcp-server-revit/src/revit_mcp_server/schemas.py`.
- When ready to call Revit APIs, dispatch the request into `ExternalEventHandler.Execute` and respond via JSON once the command finishes.
