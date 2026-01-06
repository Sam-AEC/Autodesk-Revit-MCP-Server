# Troubleshooting

- _Workspace errors_: ensure `WORKSPACE_DIR` and `MCP_REVIT_ALLOWED_DIRECTORIES` reference valid directories and the user account can read/write them.
- _Schema validation fails_: run `python -m pytest packages/mcp-server-revit/tests` to inspect failing tool inputs. Tools expect JSON payloads matching `schemas.py`.
- _Bridge connection issues_: confirm the JSON configuration file used by the MCP server points to the running add-in URL and that the add-in has started. Check `packages/revit-bridge-addin/logs` if you configure one.
- _Mock mode stubs_: use `MCP_REVIT_MODE=mock` to run all logic without Revit; the mock bridge writes deterministic dummy files in the workspace for exports.
