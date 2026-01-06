# Security Model

MCP Revit Bridge implements defense-in-depth security with workspace sandboxing, schema validation, audit logging, and safe defaults.

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│  External Client (untrusted)                                │
└─────────────────────┬───────────────────────────────────────┘
                      │ MCP Protocol (stdio)
                      │ JSON messages
┌─────────────────────▼───────────────────────────────────────┐
│  MCP Server (Python)                                        │
│  - Schema validation (Pydantic)                             │
│  - Workspace enforcement                                    │
│  - Audit logging                                            │
│  - Tool routing                                             │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP POST (localhost only)
                      │ {"tool": "...", "payload": {...}}
┌─────────────────────▼───────────────────────────────────────┐
│  Bridge Add-in (.NET)                                       │
│  - HTTP listener (127.0.0.1:3000)                           │
│  - ExternalEvent queue                                      │
│  - Revit API operations                                     │
└─────────────────────┬───────────────────────────────────────┘
                      │ Revit API
┌─────────────────────▼───────────────────────────────────────┐
│  Revit Process                                              │
│  - Document operations                                      │
│  - File I/O                                                 │
│  - Export operations                                        │
└─────────────────────────────────────────────────────────────┘
```

## Workspace Sandboxing

All file operations are restricted to allowed directories configured at server startup.

### Configuration

```python
# Environment variables
WORKSPACE_DIR = "C:\\revit-workspace"
MCP_REVIT_ALLOWED_DIRECTORIES = "C:\\revit-workspace;C:\\exports;C:\\templates"
```

### Enforcement

The `WorkspaceMonitor` class validates every file path:

```python
from revit_mcp_server.security import WorkspaceMonitor

monitor = WorkspaceMonitor(allowed_dirs=[Path("C:\\workspace")])
safe_path = monitor.validate_path("C:\\workspace\\output.csv")  # OK
unsafe_path = monitor.validate_path("C:\\system32\\file.txt")   # Raises WorkspaceViolation
```

### Path Resolution Rules

1. All paths are resolved to absolute paths
2. Symbolic links are resolved to their targets
3. Path traversal attempts (`..`, `.`) are blocked
4. Paths must be children of allowed directories (using `Path.is_relative_to()`)

### Bypass Prevention

- Paths are validated before any I/O operation
- Mock mode also enforces workspace constraints
- Validation occurs in both Python server and (planned) C# bridge

## Schema Validation

All tool inputs are validated against Pydantic models before execution.

### Input Validation

```python
from revit_mcp_server.schemas import ExportSchedulesInput

# Valid input
valid = ExportSchedulesInput(
    document_path="C:\\workspace\\model.rvt",
    schedule_names=["Door Schedule", "Window Schedule"],
    output_dir="C:\\workspace\\exports"
)

# Invalid input - raises ValidationError
invalid = ExportSchedulesInput(
    document_path=123,  # Wrong type
    schedule_names="not a list",  # Wrong type
    output_dir=None  # Missing required field
)
```

### Schema Coverage

All 25 tools have defined schemas in [schemas.py](../packages/mcp-server-revit/src/revit_mcp_server/schemas.py):

- Input schemas: Define required/optional fields, types, constraints
- Output schemas: Structure response data consistently
- Validation errors: Return clear messages to client

## Audit Logging

Every tool invocation is logged with structured data.

### Log Format

```json
{
  "timestamp": "2025-01-07T10:30:45.123Z",
  "request_id": "req_abc123",
  "tool": "revit.export_schedules",
  "payload": {
    "document_path": "C:\\workspace\\model.rvt",
    "schedule_names": ["Door Schedule"],
    "output_dir": "C:\\workspace\\exports"
  },
  "response": {
    "success": true,
    "exports": ["C:\\workspace\\exports\\Door_Schedule.csv"]
  },
  "duration_ms": 1250,
  "mode": "bridge"
}
```

### Log Location

Default: `{WORKSPACE_DIR}/audit.jsonl`

Configure with:
```bash
export MCP_REVIT_AUDIT_LOG="/var/log/revit-mcp/audit.jsonl"
```

### Log Security

- Append-only (no modification of past entries)
- Includes all tool invocations (successful and failed)
- Records file paths for output artifacts
- Tamper-evident via chronological timestamps

### Use Cases

- Compliance auditing
- Debugging failed operations
- Usage analytics
- Security incident investigation

## Safe Defaults

The server ships with secure defaults that must be explicitly relaxed.

### Default Configuration

- Mode: Not set (must be explicitly configured as `mock` or `bridge`)
- Workspace: Not set (must be configured before first use)
- Allowed directories: Empty (must be explicitly listed)
- Bridge URL: `http://localhost:3000` (localhost only, not exposed externally)
- Audit logging: Enabled (cannot be disabled)

### Network Security

The bridge HTTP listener:
- Binds only to `127.0.0.1` (localhost)
- Does not implement authentication (relies on localhost boundary)
- Does not use HTTPS (localhost traffic is trusted)
- Should never be exposed to external networks

**Do not**:
- Port forward bridge endpoint
- Bind bridge to `0.0.0.0`
- Proxy bridge through a reverse proxy accessible externally

### Destructive Operations Policy

Operations that modify models or delete data are disabled by default in mock mode and logged extensively in bridge mode.

Destructive operations:
- Model modification (element creation/deletion)
- Document saves
- File deletions
- Batch operations on multiple documents

Enable cautiously in production:
```json
{
  "allow_destructive": true,
  "destructive_confirm": true
}
```

## Tool Allow-List

While all 25 tools are exposed by default, you can restrict available tools for specific deployments.

### Configuration

```json
{
  "allowed_tools": [
    "revit.health",
    "revit.export_schedules",
    "revit.export_quantities"
  ]
}
```

Tools not in the allow-list return an error when invoked.

### Use Cases

- Limit CI/CD pipelines to read-only export operations
- Restrict automated workflows to specific QA tools
- Create role-specific tool subsets

## Mock Mode Security

Mock mode provides the same security guarantees as bridge mode without requiring Revit.

### Mock Mode Features

- Workspace sandboxing: Enforced identically to bridge mode
- Schema validation: Same Pydantic models
- Audit logging: Full request/response logging
- Deterministic outputs: Predictable mock data for testing

### CI/CD Safety

Mock mode is safe for CI environments:
- No external network access
- No Revit dependency
- No system modifications outside workspace
- Repeatable outputs for regression testing

## Security Checklist

Before deploying to production:

- [ ] Configure `WORKSPACE_DIR` to a dedicated directory
- [ ] Set `MCP_REVIT_ALLOWED_DIRECTORIES` to minimum required paths
- [ ] Verify bridge binds to `127.0.0.1` only (default)
- [ ] Review audit log location and retention policy
- [ ] Test workspace violations raise errors (not silently fail)
- [ ] Verify schema validation blocks malformed inputs
- [ ] Confirm destructive operations are appropriately restricted
- [ ] Run in mock mode first to validate configuration
- [ ] Document incident response procedures
- [ ] Set up log monitoring/alerting

## Threat Model

### In Scope

- Malicious MCP client attempting path traversal
- Untrusted input attempting to corrupt Revit models
- Unauthorized file access outside workspace
- Tool invocation without audit trail

### Out of Scope

- Physical access to machine running bridge
- Compromised Revit process
- Operating system vulnerabilities
- Revit API bugs or security issues (vendor responsibility)

## Reporting Security Issues

See [SECURITY.md](../SECURITY.md) for vulnerability reporting procedures.
