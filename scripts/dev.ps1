param(
    [string]$Workspace = "C:\\RevitProjects",
    [string]$Mode = "mock"
)

Set-Item Env:WORKSPACE_DIR $Workspace
Set-Item Env:MCP_REVIT_ALLOWED_DIRECTORIES $Workspace
Set-Item Env:MCP_REVIT_MODE $Mode
Set-Item Env:MCP_REVIT_WORKSPACE_DIR $Workspace
Write-Host "Environment configured. Run: python -m revit_mcp_server"
