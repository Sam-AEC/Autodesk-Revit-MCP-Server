# Quick Start Guide

This guide will help you get RevitMCP up and running quickly.

## Prerequisites

- Windows OS
- Autodesk Revit 2024 or 2025 installed
- Python 3.11 or later
- PowerShell 5.1 or later

## Installation Status Check

You've already installed the RevitMCP Bridge add-in. Here's what's installed:

✅ **Revit Add-in**: Installed at `C:\Users\samo3\AppData\Roaming\Autodesk\Revit\Addins\2024\RevitBridge.addin`
✅ **Bridge DLL**: Installed at `C:\ProgramData\RevitMCP\bin\RevitBridge.dll`
✅ **Configuration**: Created at `C:\ProgramData\RevitMCP\config\`

## Step 1: Verify Revit Add-in

1. **Start Revit 2024**
2. **Open any Revit project** (the bridge only works when a project is open)
3. The RevitMCP Bridge should automatically start in the background
4. Check the logs at: `C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\bridge20260107.jsonl`

### Verify Bridge is Running

In PowerShell, run:
```powershell
curl http://localhost:3000/health
```

Expected response:
```json
{
  "status": "healthy",
  "revit_version": "2024",
  "active_document": "YourProject.rvt"
}
```

**If you don't see the add-in in Revit:**
- The bridge runs silently in the background (no UI ribbon)
- Check Revit's External Tools tab - there won't be a visible button
- The add-in only creates a background HTTP server on port 3000
- Check the logs to confirm it loaded

## Step 2: Configure Python Server

The Python server configuration is now set up in the `.env` file:

```powershell
# View the configuration
cat .env
```

Edit `.env` if you need to change the workspace directories:
```
MCP_REVIT_WORKSPACE_DIR=C:\Users\samo3\Documents
MCP_REVIT_ALLOWED_DIRECTORIES=C:\Users\samo3\Documents;C:\RevitProjects
```

## Step 3: Start the Python MCP Server

Use the convenient startup script:

```powershell
.\start-server.ps1
```

This script will:
- Check if .env exists (create it if needed)
- Install Python dependencies
- Verify the Revit bridge is running
- Start the MCP server

### Alternative: Manual Start

```powershell
# Install the package
cd packages\mcp-server-revit
pip install -e .

# Set environment variables (or use .env file)
$env:MCP_REVIT_WORKSPACE_DIR="C:\Users\samo3\Documents"
$env:MCP_REVIT_ALLOWED_DIRECTORIES="C:\Users\samo3\Documents;C:\RevitProjects"
$env:MCP_REVIT_BRIDGE_URL="http://127.0.0.1:3000"
$env:MCP_REVIT_MODE="bridge"

# Run the server
python -m revit_mcp_server
```

## Step 4: Test the Setup

### Test 1: Health Check

```powershell
# In a new PowerShell window, test the bridge directly
$body = @{
    tool = "revit.health"
    payload = @{}
    request_id = "test-1"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:3000/execute" -Method POST -Body $body -ContentType "application/json"
```

### Test 2: Use the Demo Client

```powershell
cd packages\client-demo
python demo.py
```

## Troubleshooting

### Problem: "Bridge unreachable" error

**Solution:**
1. Make sure Revit is running
2. Make sure a project is open in Revit (not just Revit start screen)
3. Check if port 3000 is available: `netstat -ano | findstr :3000`
4. Check bridge logs: `C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\`

### Problem: Python server fails with "Field required" errors

**Solution:**
1. Make sure `.env` file exists in the repository root
2. Check that environment variables are set correctly
3. Run the startup script: `.\start-server.ps1`

### Problem: Add-in doesn't appear in Revit

**This is normal!** The RevitMCP Bridge doesn't show any UI in Revit. It runs silently in the background as an HTTP server.

To verify it's loaded:
1. Check the logs: `C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\`
2. Test the health endpoint: `curl http://localhost:3000/health`

### Problem: "Tool not available in bridge" error

**Solution:**
1. Make sure you're using Revit 2024 or 2025
2. Check that the bridge started successfully in the logs
3. Try calling `/tools` endpoint to see available tools:
   ```powershell
   curl http://localhost:3000/tools
   ```

## Next Steps

Once everything is working:

1. **Explore the tools**: Check [docs/api.md](docs/api.md) for all available tools
2. **Integrate with Claude Desktop**: Follow the MCP integration guide
3. **Automate workflows**: Write Python scripts using the client demo as a template
4. **Production deployment**: See [docs/admin-guide.md](docs/admin-guide.md)

## Support

- **Logs**:
  - Bridge: `C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\bridge*.jsonl`
  - MCP Server: `audit.log` in the repository root
- **Issues**: https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues
