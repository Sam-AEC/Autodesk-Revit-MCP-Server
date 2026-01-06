# Installation Guide

This guide covers installation for both mock mode (no Revit required) and bridge mode (Windows with Revit).

## Prerequisites

### Mock Mode
- Python 3.11 or later
- pip package manager
- Git

### Bridge Mode (Additional)
- Windows 10/11
- Autodesk Revit 2020-2024
- .NET Framework 4.8
- Visual Studio 2019/2022 or MSBuild tools
- Revit SDK (installed with Revit or available from Autodesk Developer Network)

## Mock Mode Setup

Mock mode runs the complete MCP server with deterministic responses, suitable for CI, testing, and development without Revit.

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_ORG/mcp-revit-bridge.git
cd mcp-revit-bridge
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

Activate the environment:
- Windows: `venv\Scripts\activate`
- Linux/Mac: `source venv/bin/activate`

### 3. Install Python Package

```bash
pip install -e packages/mcp-server-revit[dev]
```

This installs the MCP server with development dependencies (ruff, mypy, pytest).

### 4. Configure Environment

Set required environment variables:

```powershell
# PowerShell (Windows)
$env:MCP_REVIT_MODE = "mock"
$env:WORKSPACE_DIR = "C:\revit-workspace"
$env:MCP_REVIT_ALLOWED_DIRECTORIES = "C:\revit-workspace;C:\temp"
```

```bash
# Bash (Linux/Mac)
export MCP_REVIT_MODE="mock"
export WORKSPACE_DIR="/home/user/revit-workspace"
export MCP_REVIT_ALLOWED_DIRECTORIES="/home/user/revit-workspace:/tmp"
```

Or use the provided script:

```powershell
.\scripts\dev.ps1
```

### 5. Verify Installation

```bash
python -m pytest packages/mcp-server-revit/tests
```

All tests should pass.

### 6. Run Mock Server

```bash
python -m revit_mcp_server
```

The server listens on stdin/stdout for MCP protocol messages.

### 7. Run Demo Client

```bash
python packages/client-demo/demo.py
```

Expected output:
- Health check: `{"status": "healthy", "mode": "mock"}`
- Document opened: Mock response with document path
- Export quantities: Mock CSV file created in workspace
- Audit log: JSON file with request tracking

## Bridge Mode Setup

Bridge mode connects the MCP server to a running Revit instance via the .NET add-in.

### 1. Complete Mock Mode Setup

Follow steps 1-3 from Mock Mode Setup.

### 2. Set Environment Variable

```powershell
$env:REVIT_SDK = "C:\Program Files\Autodesk\Revit 2024\SDK"
```

Adjust path to your Revit version and SDK location.

### 3. Build Bridge Add-in

```powershell
.\scripts\build-addin.ps1
```

This compiles [RevitBridge.csproj](../packages/revit-bridge-addin/RevitBridge.csproj) to a DLL.

Expected output: `packages/revit-bridge-addin/bin/Release/RevitBridge.dll`

### 4. Install Add-in Manifest

```powershell
.\scripts\install-addin.ps1 -RevitYear 2024
```

This copies [RevitBridge.addin](../packages/revit-bridge-addin/RevitBridge.addin) to `%ProgramData%\Autodesk\Revit\Addins\2024\`.

### 5. Launch Revit

Start Revit. The add-in loads automatically and starts the HTTP bridge on `http://localhost:3000/`.

Verify in Revit:
- Check the Add-Ins tab for "Revit Bridge" (if UI is implemented)
- Bridge server runs silently in background

### 6. Configure MCP Server for Bridge Mode

Update environment:

```powershell
$env:MCP_REVIT_MODE = "bridge"
$env:MCP_REVIT_BRIDGE_URL = "http://localhost:3000"
```

Or edit [examples/revit-mcp-config.json](../examples/revit-mcp-config.json):

```json
{
  "mode": "bridge",
  "bridge_url": "http://localhost:3000",
  "workspace_dir": "C:\\revit-workspace",
  "allowed_directories": ["C:\\revit-workspace"]
}
```

### 7. Run Bridge Server

```bash
python -m revit_mcp_server
```

### 8. Run Demo Client

```bash
python packages/client-demo/demo.py
```

Expected output:
- Health check: `{"status": "healthy", "mode": "bridge", "revit_version": "2024"}`
- Real Revit operations execute via the bridge

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_REVIT_MODE` | Yes | - | `mock` or `bridge` |
| `WORKSPACE_DIR` | Yes | - | Root directory for file operations |
| `MCP_REVIT_ALLOWED_DIRECTORIES` | Yes | - | Semicolon-separated list of allowed paths |
| `MCP_REVIT_BRIDGE_URL` | Bridge only | `http://localhost:3000` | Bridge HTTP endpoint |
| `MCP_REVIT_AUDIT_LOG` | No | `workspace/audit.jsonl` | Audit log file path |
| `REVIT_SDK` | Build only | - | Path to Revit SDK for building add-in |

### Configuration File

Alternative to environment variables: use a JSON config file.

```json
{
  "mode": "mock",
  "workspace_dir": "/path/to/workspace",
  "allowed_directories": ["/path/to/workspace", "/path/to/data"],
  "bridge_url": "http://localhost:3000",
  "audit_log": "workspace/audit.jsonl"
}
```

Load with:

```bash
python -m revit_mcp_server --config examples/revit-mcp-config.json
```

## Troubleshooting

### Issue: Workspace Violation Error

**Error**: `WorkspaceViolation: Path outside allowed directories`

**Fix**:
1. Verify `WORKSPACE_DIR` and `MCP_REVIT_ALLOWED_DIRECTORIES` are set
2. Ensure paths use absolute paths (not relative)
3. On Windows, use double backslashes or forward slashes: `C:\\workspace` or `C:/workspace`
4. Check directory exists and has read/write permissions

### Issue: Schema Validation Failed

**Error**: `SchemaValidationError: Field 'document_path' is required`

**Fix**:
1. Check tool input matches schema in [docs/tools.md](tools.md)
2. Review error message for missing/invalid fields
3. Run tests to see valid examples: `pytest packages/mcp-server-revit/tests/test_tools.py -v`

### Issue: Bridge Connection Refused

**Error**: `BridgeError: Connection refused to http://localhost:3000`

**Fix**:
1. Verify Revit is running with the add-in loaded
2. Check add-in manifest is installed: `%ProgramData%\Autodesk\Revit\Addins\2024\RevitBridge.addin`
3. Verify DLL path in manifest points to the built DLL
4. Check Windows Firewall isn't blocking localhost:3000
5. Review Revit Journal file for add-in load errors

### Issue: Add-in Build Failed

**Error**: `MSBuild error: RevitAPI reference not found`

**Fix**:
1. Set `REVIT_SDK` environment variable to correct SDK path
2. Verify Revit SDK is installed (comes with Revit or download separately)
3. Check [RevitBridge.csproj](../packages/revit-bridge-addin/RevitBridge.csproj) references match your Revit version
4. Ensure Visual Studio or MSBuild tools are installed

### Issue: Mock Mode Files Not Created

**Error**: Export tools don't create output files in mock mode

**Fix**:
1. Verify `WORKSPACE_DIR` exists and is writable
2. Check `MCP_REVIT_MODE=mock` is set
3. Review audit log for errors: `cat workspace/audit.jsonl`
4. Ensure no file permission issues in workspace directory

## Next Steps

- Review [tool catalog](tools.md) for available operations
- Understand [architecture](architecture.md) and trust boundaries
- Read [security model](security.md) for production deployments
- Explore [examples](../examples/) for workflow configurations
