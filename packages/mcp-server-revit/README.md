# Autodesk Revit MCP Server (Python Package)

Python package for the Autodesk Revit MCP server used by AI clients over stdio.

- Repository: https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server
- MCP entrypoint: `python -m revit_mcp_server.mcp_server`
- Console script: `revit-mcp-server`
- Requires Python 3.11+

Environment variables (prefix `MCP_REVIT_`) include:

- `WORKSPACE_DIR`
- `ALLOWED_DIRECTORIES`
- `MODE` (`mock` or `bridge`)
- `BRIDGE_URL` (required for `bridge` mode)
- `AUDIT_LOG`
- `LOG_LEVEL`

<!-- mcp-name: io.github.Sam-AEC/autodesk-revit-mcp-server -->

