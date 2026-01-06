# Installation

1. Set up Python 3.11 and create a virtual environment.
2. Install the MCP server: `pip install -e packages/mcp-server-revit[dev]`.
3. Configure the workspace: set `MCP_REVIT_ALLOWED_DIRECTORIES` and `WORKSPACE_DIR` to the paths where Revit files live.
4. For mock testing, set `MCP_REVIT_MODE=mock`. For bridge mode, build the add-in via `packages/revit-bridge-addin/scripts/build-addin.ps1` and deploy using `install-addin.ps1` with the correct Revit year.
5. Use `scripts/dev.ps1` or `scripts/run-server.ps1` to launch the server with the proper environment variables.
