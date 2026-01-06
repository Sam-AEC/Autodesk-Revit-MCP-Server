# Revit Bridge Add-in

This `.NET 4.8` add-in exposes the Revit-focused MCP toolset through two pieces:

- `BridgeServer` listens on `http://localhost:3000/` and converts `{ "tool": "...", "payload": {...} }` payloads into bridge commands via `BridgeCommandFactory`.
- `ExternalEventHandler` establishes an execution queue; future iterations can enqueue actual Revit operations and marshal them through the Revit API.

Build the project with `scripts/build-addin.ps1` (set `REVIT_SDK`) and install the manifest to `%ProgramData%\Autodesk\Revit\Addins\<year>` with `scripts/install-addin.ps1`. The add-in currently returns deterministic stub responses for all 25 tools; extend `BridgeCommandFactory` and the `ExternalEventHandler` to run real Revit logic.
