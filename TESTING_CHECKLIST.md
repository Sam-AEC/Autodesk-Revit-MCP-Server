# Testing Checklist for RevitMCP

Use this checklist to verify your RevitMCP installation is working correctly.

## Prerequisites Check

- [ ] Windows OS
- [ ] Revit 2024 or 2025 installed
- [ ] Python 3.11+ installed (`python --version`)
- [ ] PowerShell 5.1+ available

## Installation Verification

### 1. Check Revit Add-in Files

```powershell
# Check if add-in manifest exists
Test-Path "C:\Users\samo3\AppData\Roaming\Autodesk\Revit\Addins\2024\RevitBridge.addin"

# Check if DLL exists
Test-Path "C:\ProgramData\RevitMCP\bin\RevitBridge.dll"

# View add-in manifest
cat "C:\Users\samo3\AppData\Roaming\Autodesk\Revit\Addins\2024\RevitBridge.addin"
```

**Expected**: All files should exist ✅

### 2. Check Python Configuration

```powershell
# Navigate to repository
cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"

# Check .env file exists
Test-Path .env

# View configuration
cat .env
```

**Expected**: `.env` file exists with valid paths ✅

### 3. Install Python Package

```powershell
# Install in development mode
cd packages\mcp-server-revit
pip install -e .
```

**Expected**: Installation succeeds without errors ✅

## Revit Bridge Testing

### 1. Start Revit

- [ ] Open Revit 2024
- [ ] Open ANY project file (not just the start screen)
- [ ] Wait for project to fully load

### 2. Check Bridge Logs

```powershell
# View recent logs
Get-Content "C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\bridge*.jsonl" -Tail 20
```

**Expected output**:
```
2026-01-07 XX:XX:XX.XXX +01:00 [INF] BridgeServer started on http://127.0.0.1:3000/
2026-01-07 XX:XX:XX.XXX +01:00 [INF] RevitMCP Bridge started for Revit 2024
```

### 3. Test Bridge Health Endpoint

```powershell
# Test health check
curl http://localhost:3000/health
```

**Expected response**:
```json
{
  "status": "healthy",
  "revit_version": "2024",
  "active_document": "YourProject.rvt"
}
```

### 4. Test Tools Endpoint

```powershell
# Get list of available tools
curl http://localhost:3000/tools
```

**Expected**: JSON response with list of ~25 tools ✅

### 5. Test Tool Execution

```powershell
# Test a simple tool
$body = @{
    tool = "revit.health"
    payload = @{}
    request_id = "test-1"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:3000/execute" -Method POST -Body $body -ContentType "application/json"
```

**Expected**: JSON response with status and Revit info ✅

## Python MCP Server Testing

### 1. Start Server (Without Revit)

```powershell
# From repository root
cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"

# Try starting in mock mode
$env:MCP_REVIT_MODE="mock"
python -m revit_mcp_server
```

**Expected**: Server starts and shows "Revit MCP server started. Awaiting JSON requests." ✅

Press Ctrl+C to stop.

### 2. Start Server (With Revit)

Make sure Revit is running with a project open, then:

```powershell
# Use the startup script
.\start-server.ps1
```

**Expected output**:
```
RevitMCP Server Startup
=====================

Configuration:
  MCP_REVIT_WORKSPACE_DIR=C:\Users\samo3\Documents
  ...

Checking Revit bridge...
Bridge status: healthy
Revit version: 2024

========================================
Starting MCP Server (mode: bridge)
========================================

Revit MCP server started. Awaiting JSON requests.
```

### 3. Test Server with JSON Request

In a separate PowerShell window while the server is running:

```powershell
# Send a test request to stdin
$request = @{
    tool = "revit.health"
    payload = @{}
} | ConvertTo-Json -Compress

echo $request | python -m revit_mcp_server
```

**Expected**: JSON response on stdout ✅

### 4. Test with Demo Client

```powershell
cd packages\client-demo
python demo.py
```

**Expected**: Successful execution of demo operations ✅

## Common Issues and Solutions

### Issue 1: "Field required" errors

**Symptom**:
```
ValidationError: 2 validation errors for Config
workspace_dir
  Field required
```

**Solution**:
```powershell
# Create .env from example
copy .env.example .env

# Edit .env with your paths
notepad .env

# Or use the startup script which does this automatically
.\start-server.ps1
```

### Issue 2: "Bridge unreachable"

**Symptom**:
```
BridgeError: Bridge unreachable at http://127.0.0.1:3000
```

**Solution Checklist**:
- [ ] Revit is running
- [ ] A project is OPEN in Revit (not just start screen)
- [ ] Check if port 3000 is available: `netstat -ano | findstr :3000`
- [ ] Check bridge logs: `Get-Content "C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\bridge*.jsonl" -Tail 10`
- [ ] Restart Revit

### Issue 3: Add-in not loading

**Symptom**: No logs in RevitMCP\Logs folder

**Solution**:
```powershell
# Check if .addin file exists
Test-Path "C:\Users\samo3\AppData\Roaming\Autodesk\Revit\Addins\2024\RevitBridge.addin"

# Check if DLL exists
Test-Path "C:\ProgramData\RevitMCP\bin\RevitBridge.dll"

# Check Revit journal for errors
Get-Content "$env:LOCALAPPDATA\Autodesk\Revit\Autodesk Revit 2024\Journals\*.txt" -Tail 50 | Select-String -Pattern "RevitMCP|RevitBridge"

# If files missing, reinstall
cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"
.\scripts\install.ps1 -RevitVersion 2024
```

### Issue 4: Python module not found

**Symptom**:
```
ModuleNotFoundError: No module named 'revit_mcp_server'
```

**Solution**:
```powershell
# Install package in development mode
cd packages\mcp-server-revit
pip install -e .
```

### Issue 5: "Path does not point to a directory"

**Symptom**:
```
Path does not point to a directory [type=path_not_directory, input_value=WindowsPath('C:/RevitProjects')]
```

**Solution**:
```powershell
# Edit .env to only include existing directories
notepad .env

# Make sure the directories actually exist
New-Item -ItemType Directory -Path "C:\RevitProjects" -Force
```

## Performance Testing

### Test 1: Bridge Response Time

```powershell
# Measure health check response time
Measure-Command { curl http://localhost:3000/health }
```

**Expected**: < 100ms ✅

### Test 2: Tool Execution Time

```powershell
# Measure tool execution
$body = @{tool="revit.health"; payload=@{}; request_id="perf-test"} | ConvertTo-Json
Measure-Command {
    Invoke-RestMethod -Uri "http://localhost:3000/execute" -Method POST -Body $body -ContentType "application/json"
}
```

**Expected**: < 500ms for simple tools ✅

## Integration Testing

### Test with Multiple Tools

```powershell
# Test listing views
$body = @{
    tool = "revit.list_views"
    payload = @{}
    request_id = "test-views"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:3000/execute" -Method POST -Body $body -ContentType "application/json"
```

**Expected**: List of views from active Revit document ✅

## Final Checklist

- [ ] Revit add-in loads without errors
- [ ] Bridge responds to health checks
- [ ] Python server starts without errors
- [ ] Can execute tools through bridge
- [ ] Logs are being written correctly
- [ ] Configuration is properly loaded from .env

## Quick Commands Reference

```powershell
# Start everything
1. Open Revit + project
2. cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"
3. .\start-server.ps1

# Test bridge
curl http://localhost:3000/health

# View logs
Get-Content "C:\Users\samo3\AppData\Roaming\RevitMCP\Logs\bridge*.jsonl" -Tail 20

# Stop server
Press Ctrl+C in server window

# Reinstall add-in
.\scripts\install.ps1 -RevitVersion 2024

# Rebuild C# add-in
.\scripts\build-addin.ps1 -RevitVersion 2024
```

---

**If all items are checked, your installation is complete and working!** 🎉

For additional help, see:
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [FIXES_APPLIED.md](FIXES_APPLIED.md) - What was fixed
- [README.md](README.md) - Full documentation
