# Test MCP Server Standalone
# This runs the server exactly how Claude Desktop would run it

Write-Host "`nTesting MCP Server in Claude Desktop Mode`n" -ForegroundColor Cyan

# Set environment variables exactly as Claude Desktop would
$env:MCP_REVIT_WORKSPACE_DIR = "C:\Users\samo3\Documents"
$env:MCP_REVIT_ALLOWED_DIRECTORIES = "C:\Users\samo3\Documents"
$env:MCP_REVIT_BRIDGE_URL = "http://127.0.0.1:3000"
$env:MCP_REVIT_MODE = "bridge"

Write-Host "Environment variables set:" -ForegroundColor Yellow
Write-Host "  MCP_REVIT_WORKSPACE_DIR = $env:MCP_REVIT_WORKSPACE_DIR" -ForegroundColor Gray
Write-Host "  MCP_REVIT_BRIDGE_URL = $env:MCP_REVIT_BRIDGE_URL" -ForegroundColor Gray
Write-Host "  MCP_REVIT_MODE = $env:MCP_REVIT_MODE" -ForegroundColor Gray

Write-Host "`nStarting MCP server..." -ForegroundColor Yellow
Write-Host "Command: python -m revit_mcp_server.mcp_server" -ForegroundColor Gray
Write-Host "`nPress Ctrl+C to stop`n" -ForegroundColor Yellow
Write-Host "="*70 -ForegroundColor Cyan

# Change to repo directory
Set-Location "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"

# Run the server
try {
    & "C:\Users\samo3\AppData\Local\Programs\Python\Python313\python.exe" -m revit_mcp_server.mcp_server
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
}
