# Architecture

MCP Revit Bridge is a two-tier system connecting MCP clients to Autodesk Revit through a Python server and .NET bridge add-in.

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  MCP Client (Claude Desktop, custom apps, automation scripts)   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             │ MCP Protocol (stdio)
                             │ JSON-RPC messages
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  MCP Server (Python)                                             │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ Schema         │  │ Workspace    │  │ Audit              │   │
│  │ Validation     │  │ Sandbox      │  │ Recorder           │   │
│  │ (Pydantic)     │  │ (pathlib)    │  │ (JSONL logs)       │   │
│  └────────────────┘  └──────────────┘  └────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Tool Handlers (25 tools)                                 │   │
│  │ - revit.health, revit.open_document, revit.export_*      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Bridge Client                                            │   │
│  │ ┌────────────────┐         ┌────────────────────────┐    │   │
│  │ │ Mock Bridge    │   OR    │ HTTP Client (httpx)    │    │   │
│  │ │ (deterministic)│         │ -> localhost:3000      │    │   │
│  │ └────────────────┘         └────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             │ HTTP POST (localhost only)
                             │ {"tool": "...", "payload": {...}}
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  Revit Bridge Add-in (.NET 4.8)                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ BridgeServer (HttpListener on 127.0.0.1:3000)           │   │
│  └────────────────────────────┬─────────────────────────────┘   │
│                               │                                  │
│  ┌────────────────────────────▼─────────────────────────────┐   │
│  │ BridgeCommandFactory (tool router)                       │   │
│  │ - Routes tool requests to handlers                       │   │
│  │ - Serializes/deserializes JSON                           │   │
│  └────────────────────────────┬─────────────────────────────┘   │
│                               │                                  │
│  ┌────────────────────────────▼─────────────────────────────┐   │
│  │ ExternalEventHandler (Revit API queue)                   │   │
│  │ - Queues operations on UI thread                         │   │
│  │ - Executes Revit API calls safely                        │   │
│  └────────────────────────────┬─────────────────────────────┘   │
└────────────────────────────────┼─────────────────────────────────┘
                                 │
                                 │ Revit API
                                 │
┌────────────────────────────────▼─────────────────────────────────┐
│  Autodesk Revit (2020-2024)                                      │
│  - Document operations                                           │
│  - Element queries and modifications                             │
│  - Export operations (PDF, DWG, IFC, CSV)                        │
│  - QA metric calculations                                        │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### MCP Server (Python)

**Location**: [packages/mcp-server-revit/](../packages/mcp-server-revit/)

**Responsibilities**:
- Listen for MCP protocol messages on stdin/stdout
- Validate tool inputs against JSON schemas (Pydantic)
- Enforce workspace sandboxing (all file paths within allowed directories)
- Route tool requests to appropriate handlers
- Record audit logs for every invocation
- Communicate with bridge (HTTP) or mock implementation

**Key Modules**:
- [server.py](../packages/mcp-server-revit/src/revit_mcp_server/server.py): Main MCP protocol handler
- [config.py](../packages/mcp-server-revit/src/revit_mcp_server/config.py): Environment-based configuration
- [schemas.py](../packages/mcp-server-revit/src/revit_mcp_server/schemas.py): Pydantic models for all 25 tools
- [tools/handlers.py](../packages/mcp-server-revit/src/revit_mcp_server/tools/handlers.py): Tool implementation functions
- [security/workspace.py](../packages/mcp-server-revit/src/revit_mcp_server/security/workspace.py): Path validation
- [security/audit.py](../packages/mcp-server-revit/src/revit_mcp_server/security/audit.py): Audit log writing
- [bridge/client.py](../packages/mcp-server-revit/src/revit_mcp_server/bridge/client.py): HTTP bridge client
- [bridge/mock.py](../packages/mcp-server-revit/src/revit_mcp_server/bridge/mock.py): Deterministic mock responses

**Configuration**:
```bash
MCP_REVIT_MODE=mock|bridge          # Execution mode
WORKSPACE_DIR=/path/to/workspace    # Root directory for file operations
MCP_REVIT_ALLOWED_DIRECTORIES=...   # Colon/semicolon-separated paths
MCP_REVIT_BRIDGE_URL=http://...     # Bridge HTTP endpoint (bridge mode only)
MCP_REVIT_AUDIT_LOG=/path/to/log    # Audit log file
```

### Revit Bridge Add-in (.NET)

**Location**: [packages/revit-bridge-addin/](../packages/revit-bridge-addin/)

**Responsibilities**:
- Start HTTP listener on Revit startup (IExternalApplication)
- Accept JSON POST requests from MCP server
- Queue operations on Revit UI thread via ExternalEvent
- Execute Revit API operations
- Return JSON responses to MCP server

**Key Classes**:
- [App.cs](../packages/revit-bridge-addin/src/Bridge/App.cs): Add-in entry point (IExternalApplication)
- [BridgeServer.cs](../packages/revit-bridge-addin/src/Bridge/BridgeServer.cs): HTTP listener (HttpListener on port 3000)
- [BridgeCommandFactory.cs](../packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs): Tool request router
- [ExternalEventHandler.cs](../packages/revit-bridge-addin/src/Bridge/ExternalEventHandler.cs): Revit API execution queue

**Deployment**:
1. Build with MSBuild or Visual Studio
2. Output DLL: `packages/revit-bridge-addin/bin/Release/RevitBridge.dll`
3. Manifest file: [RevitBridge.addin](../packages/revit-bridge-addin/RevitBridge.addin)
4. Install to: `%ProgramData%\Autodesk\Revit\Addins\{year}\RevitBridge.addin`

**Communication Protocol**:

Request format:
```json
POST http://localhost:3000/
Content-Type: application/json

{
  "tool": "revit.export_schedules",
  "payload": {
    "request_id": "req_001",
    "output_path": "C:\\workspace\\schedules.csv"
  }
}
```

Response format:
```json
{
  "schedules": ["Door Schedule", "Window Schedule"],
  "output_path": "C:\\workspace\\schedules.csv"
}
```

Error response:
```json
{
  "error": "RevitAPIException",
  "message": "Failed to export schedule: Document not open"
}
```

## Execution Models

### Mock Mode

**Use case**: CI/CD, testing, development without Revit

**Behavior**:
- All tools return deterministic stub responses
- No bridge HTTP communication
- Workspace sandboxing still enforced
- Audit logging still active

**Advantages**:
- No Windows/Revit dependency
- Fast execution (no I/O delays)
- Repeatable outputs for regression tests
- Safe for automated pipelines

**Configuration**:
```bash
export MCP_REVIT_MODE=mock
```

### Bridge Mode

**Use case**: Production Revit automation

**Behavior**:
- MCP server sends HTTP requests to bridge
- Bridge queues operations on Revit UI thread
- Real Revit API operations execute
- Actual files generated (CSV, PDF, DWG, IFC)

**Requirements**:
- Windows 10/11
- Revit 2020-2024 running
- Bridge add-in installed and loaded

**Configuration**:
```bash
export MCP_REVIT_MODE=bridge
export MCP_REVIT_BRIDGE_URL=http://localhost:3000
```

## Why the Bridge Exists

### Revit API Constraints

1. **UI Thread Requirement**: Most Revit API operations must run on the main UI thread
2. **External Event Pattern**: Out-of-process calls must use `IExternalEventHandler`
3. **.NET Framework Dependency**: Revit API requires .NET 4.8 (not .NET Core)
4. **Windows-Only**: Revit runs exclusively on Windows

### Design Decisions

**Why not Python → Revit directly?**
- Revit API is .NET only
- pythonnet/.NET interop is complex and fragile
- Process boundary provides cleaner separation

**Why HTTP instead of named pipes/IPC?**
- Simple debugging (curl/Postman can test bridge)
- No Windows-specific IPC complexity
- HTTP is language-agnostic for future clients
- Localhost-only binding is secure

**Why separate add-in instead of Revit macros?**
- Add-ins start automatically with Revit
- No manual macro execution required
- Persistent HTTP listener across sessions
- Better error handling and logging

## Trust Boundaries

### Boundary 1: MCP Client → MCP Server

**Threat**: Malicious client sends path traversal attacks

**Mitigation**:
- Schema validation rejects malformed inputs
- Workspace sandbox blocks paths outside allowed directories
- All file paths resolved to absolute paths before validation

### Boundary 2: MCP Server → Bridge

**Threat**: Compromised bridge returns malicious data

**Mitigation**:
- Bridge runs on localhost only (127.0.0.1)
- No authentication needed (same-machine trust)
- Responses validated against output schemas
- Audit log records all bridge communications

### Boundary 3: Bridge → Revit

**Threat**: Bridge exploits Revit API vulnerabilities

**Mitigation**:
- ExternalEvent enforces UI thread execution
- Revit API's own security model applies
- Document operations respect Revit's file permissions
- Bridge cannot execute arbitrary code

## Scaling and Performance

### Current Limitations

- Single-threaded bridge (one request at a time)
- Synchronous HTTP requests (blocking)
- No request queuing or batching
- Each tool invocation is independent

### Future Improvements

- Async HTTP client in MCP server
- Request queue in bridge with parallel execution
- Batch operations (e.g., export 100 sheets in one call)
- Persistent document cache (avoid repeated opening)

## Testing Strategy

### Unit Tests

**Location**: [packages/mcp-server-revit/tests/](../packages/mcp-server-revit/tests/)

**Coverage**:
- Schema validation (valid/invalid inputs)
- Workspace path enforcement
- Tool handler registration
- Mock bridge responses

**Run**:
```bash
pytest packages/mcp-server-revit/tests
```

### Integration Tests

**Approach**: Use mock mode to test end-to-end without Revit

```python
# Set mock mode
os.environ["MCP_REVIT_MODE"] = "mock"

# Run server and send MCP messages
response = mcp_server.handle_tool_request({
    "tool": "revit.export_schedules",
    "payload": {"request_id": "test_001", "output_path": "/workspace/test.csv"}
})

# Validate response matches schema
assert "schedules" in response
assert response["output_path"] == "/workspace/test.csv"
```

### Manual Testing (Bridge Mode)

1. Build and install bridge add-in
2. Start Revit
3. Verify HTTP listener: `curl http://localhost:3000/`
4. Run demo client: `python packages/client-demo/demo.py`
5. Check audit log for recorded requests

## Security Considerations

See [security.md](security.md) for comprehensive security model.

**Key points**:
- All file paths sandboxed to allowed directories
- Bridge binds to localhost only (no external exposure)
- Audit logs record every tool invocation
- Schema validation prevents injection attacks
- Mock mode safe for untrusted CI environments

## Extending the System

### Adding a New Tool

1. Define input/output schemas in [schemas.py](../packages/mcp-server-revit/src/revit_mcp_server/schemas.py):
```python
class MyToolInput(RequestPayload):
    document_id: str
    parameter_name: str

class MyToolOutput(BaseModel):
    value: str
```

2. Implement handler in [handlers.py](../packages/mcp-server-revit/src/revit_mcp_server/tools/handlers.py):
```python
def my_tool(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = MyToolInput(**payload)
    # Mock implementation
    return MyToolOutput(value="mock_result").model_dump()
```

3. Register in `TOOL_HANDLERS`:
```python
TOOL_HANDLERS["revit.my_tool"] = my_tool
```

4. Update bridge [BridgeCommandFactory.cs](../packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs):
```csharp
case "revit.my_tool":
    // Revit API implementation
    var doc = GetActiveDocument();
    var param = GetParameter(doc, payload["parameter_name"]);
    return new { value = param.AsString() };
```

5. Add tests in [test_tools.py](../packages/mcp-server-revit/tests/test_tools.py)

6. Document in [tools.md](tools.md)

## Deployment Topologies

### Local Development

```
Developer Machine:
  - Revit 2024
  - Bridge add-in
  - MCP server (Python venv)
  - Demo client
```

### CI/CD Pipeline

```
GitHub Actions (Windows runner):
  - MCP server (mock mode)
  - Pytest
  - No Revit dependency
```

### Production Automation

```
Dedicated Windows Server:
  - Revit 2024 (licensed)
  - Bridge add-in (installed)
  - MCP server (systemd/Windows service)
  - Cron/scheduled tasks invoke demo client
  - Audit logs → monitoring system
```

## Troubleshooting

### Bridge Not Responding

**Symptoms**: MCP server reports "Connection refused"

**Diagnosis**:
1. Check Revit is running
2. Verify add-in loaded: Check Revit Journal file
3. Test bridge directly: `curl http://localhost:3000/`
4. Review add-in manifest path in `RevitBridge.addin`

### Workspace Violations

**Symptoms**: `WorkspaceViolation` errors

**Diagnosis**:
1. Print allowed directories: `echo $MCP_REVIT_ALLOWED_DIRECTORIES`
2. Verify paths are absolute
3. Check path separators (Windows: `\\` or `/`)
4. Ensure directories exist and are readable

### Schema Validation Failures

**Symptoms**: `SchemaValidationError` on tool invocation

**Diagnosis**:
1. Review tool schema in [tools.md](tools.md)
2. Check required vs optional fields
3. Validate JSON syntax
4. Review error message for specific field issues

See [install.md](install.md) for additional troubleshooting.
