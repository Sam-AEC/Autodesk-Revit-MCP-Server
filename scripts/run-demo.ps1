param(
    [string]$Workspace = "C:\RevitProjects",
    [string]$Mode = "mock"
)

Set-Item Env:WORKSPACE_DIR $Workspace
Set-Item Env:MCP_REVIT_WORKSPACE_DIR $Workspace
Set-Item Env:MCP_REVIT_ALLOWED_DIRECTORIES $Workspace
Set-Item Env:MCP_REVIT_MODE $Mode
Set-Item Env:MCP_REVIT_BRIDGE_URL "http://localhost:3000"

Write-Host "Launching Revit MCP server in $Mode mode with workspace $Workspace"
python -m revit_mcp_server
