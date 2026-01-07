# Force Reload Claude Desktop MCP Servers

## Current Issue
The "revit" server is configured correctly in the config file but not appearing in Claude Desktop's "Local MCP servers" list.

## Solution: Force Full Restart

### Method 1: Complete Shutdown (Recommended)

**Windows:**
1. Close Claude Desktop window
2. Open Task Manager (Ctrl+Shift+Esc)
3. Look for any "Claude" processes
4. Right-click each and select "End Task"
5. Wait 5 seconds
6. Restart Claude Desktop
7. Go to Settings > Developer > Local MCP servers

### Method 2: Clear Cache & Restart

1. Close Claude Desktop completely
2. Delete cache folder:
   ```
   %LOCALAPPDATA%\Claude\Cache
   ```
3. Restart Claude Desktop

### Method 3: Reload Configuration

In Claude Desktop:
1. Go to Settings > Developer
2. Click "Reload" next to "Local MCP servers"
3. The revit server should appear

## Verify Config is Valid

Your config file should look EXACTLY like this:

```json
{
  "mcpServers": {
    "revit": {
      "command": "C:\\Users\\samo3\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
      "args": [
        "-m",
        "revit_mcp_server.mcp_server"
      ],
      "env": {
        "MCP_REVIT_WORKSPACE_DIR": "C:\\Users\\samo3\\Documents",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\Users\\samo3\\Documents",
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
        "MCP_REVIT_MODE": "bridge"
      }
    }
  }
}
```

Location: `C:\Users\samo3\AppData\Roaming\Claude\claude_desktop_config.json`

## Check for JSON Syntax Errors

Run this to validate:

```powershell
$config = Get-Content "$env:APPDATA\Claude\claude_desktop_config.json" -Raw | ConvertFrom-Json
if ($config.mcpServers.revit) {
    Write-Host "Config is valid!" -ForegroundColor Green
} else {
    Write-Host "Config missing revit server!" -ForegroundColor Red
}
```

## Check Developer Console

1. In Claude Desktop: View > Toggle Developer Tools
2. Click "Console" tab
3. Look for errors when starting up
4. Common errors to look for:
   - "Cannot find module"
   - "Python not found"
   - "mcp-server startup failed"

## Manual Test

Test if the server can start:

```powershell
cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"
python -m revit_mcp_server.mcp_server
```

Should start without errors (press Ctrl+C to stop)

## If Still Not Appearing

The issue might be:

1. **Python path wrong**: Verify Python path matches in config
2. **Module not installed**: Reinstall the package
3. **Claude Desktop version**: Make sure you have latest version
4. **Permissions**: Run Claude Desktop as administrator (once)

## Quick Fix Command

Run this to reinstall everything:

```powershell
cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"
.\setup-claude-desktop.ps1 -Force
```

Then completely restart Claude Desktop.
