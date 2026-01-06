# Tool Catalog

MCP Revit Bridge exposes 25 tools organized into five categories: health checks, document operations, QA audits, export operations, and automation workflows.

All tools accept JSON inputs validated against Pydantic schemas and return structured JSON responses.

## Tool Categories

- [Health & Status](#health--status)
- [Document Operations](#document-operations)
- [QA & Audits](#qa--audits)
- [Export Operations](#export-operations)
- [Sheet Automation](#sheet-automation)
- [Baseline Tracking](#baseline-tracking)

---

## Health & Status

### revit.health

**Purpose**: Check bridge connectivity and server health

**Input Schema**:
```json
{
  "request_id": "req_001",
  "check_interval": 30
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_id` | string | Yes | Unique request identifier |
| `check_interval` | integer | No | Seconds between retries (default: 30) |

**Output Schema**:
```json
{
  "status": "healthy",
  "requests_handled": 1,
  "message": "Bridge ready"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | enum | `healthy`, `degraded`, or `failing` |
| `requests_handled` | integer | Request count since startup |
| `message` | string | Human-readable status message |

**Example Request/Response**:
```json
// Request
{
  "tool": "revit.health",
  "payload": {
    "request_id": "health_check_001"
  }
}

// Response
{
  "status": "healthy",
  "requests_handled": 42,
  "message": "Bridge connectivity is verified."
}
```

---

## Document Operations

### revit.open_document

**Purpose**: Open a Revit document (.rvt or .rfa)

**Input Schema**:
```json
{
  "request_id": "req_002",
  "file_path": "C:\\workspace\\project.rvt",
  "detach": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_id` | string | Yes | Unique request identifier |
| `file_path` | string | Yes | Absolute path to Revit document (must be in allowed directories) |
| `detach` | boolean | No | Detach from central (default: false) |

**Output Schema**:
```json
{
  "document_id": "project",
  "title": "project.rvt",
  "model_path": "C:\\workspace\\project.rvt"
}
```

**Example Request/Response**:
```json
// Request
{
  "tool": "revit.open_document",
  "payload": {
    "request_id": "open_001",
    "file_path": "C:\\workspace\\hospital_model.rvt",
    "detach": true
  }
}

// Response
{
  "document_id": "hospital_model",
  "title": "hospital_model.rvt",
  "model_path": "C:\\workspace\\hospital_model.rvt"
}
```

### revit.list_views

**Purpose**: List all views in the active or specified document

**Input Schema**:
```json
{
  "request_id": "req_003",
  "document_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_id` | string | Yes | Unique request identifier |
| `document_id` | string | No | Document ID (null = active document) |

**Output Schema**:
```json
{
  "views": [
    {
      "view_id": "view-1",
      "name": "Floor Plan - Level 1",
      "discipline": "Architectural"
    }
  ]
}
```

**Example Request/Response**:
```json
// Request
{
  "tool": "revit.list_views",
  "payload": {
    "request_id": "list_views_001"
  }
}

// Response
{
  "views": [
    {"view_id": "view-1", "name": "Floor Plan", "discipline": "Architectural"},
    {"view_id": "view-2", "name": "Ceiling Plan", "discipline": "Mechanical"}
  ]
}
```

---

## QA & Audits

All audit tools share a common input/output schema.

**Common Input Schema**:
```json
{
  "request_id": "req_004",
  "document_id": null
}
```

**Common Output Schema**:
```json
{
  "issues_found": 0,
  "severity": "info"
}
```

### revit.model_health_summary

**Purpose**: Generate overall model health report (warnings, errors, performance)

### revit.warning_triage_report

**Purpose**: Categorize and prioritize Revit warnings

### revit.naming_standards_audit

**Purpose**: Validate element names against naming conventions

### revit.parameter_compliance_audit

**Purpose**: Check required parameters are populated

### revit.shared_parameter_binding_audit

**Purpose**: Verify shared parameter bindings and consistency

### revit.view_template_compliance_check

**Purpose**: Audit views for template application

### revit.tag_coverage_audit

**Purpose**: Identify untagged elements

### revit.room_space_completeness_report

**Purpose**: Check room/space data completeness

### revit.link_monitor_report

**Purpose**: Audit linked file status and paths

### revit.coordinate_sanity_check

**Purpose**: Validate project coordinates and survey points

**Example Request/Response** (any audit tool):
```json
// Request
{
  "tool": "revit.naming_standards_audit",
  "payload": {
    "request_id": "audit_001"
  }
}

// Response
{
  "issues_found": 12,
  "severity": "warning"
}
```

---

## Export Operations

### revit.export_schedules

**Purpose**: Export schedules to CSV files

**Input Schema**:
```json
{
  "request_id": "req_005",
  "output_path": "C:\\workspace\\exports\\schedules.csv"
}
```

**Output Schema**:
```json
{
  "schedules": ["Door Schedule", "Window Schedule"],
  "output_path": "C:\\workspace\\exports\\schedules.csv"
}
```

**Example**:
```json
// Request
{
  "tool": "revit.export_schedules",
  "payload": {
    "request_id": "export_sched_001",
    "output_path": "C:\\workspace\\door_schedule.csv"
  }
}

// Response
{
  "schedules": ["Door Schedule"],
  "output_path": "C:\\workspace\\door_schedule.csv"
}
```

### revit.export_quantities

**Purpose**: Export material quantities/takeoffs to CSV

**Input Schema**:
```json
{
  "request_id": "req_006",
  "output_path": "C:\\workspace\\quantities.csv"
}
```

**Output Schema**:
```json
{
  "categories_exported": 5,
  "output_path": "C:\\workspace\\quantities.csv"
}
```

### revit.export_pdf_by_sheet_set

**Purpose**: Export sheets to PDF based on sheet set configuration

**Input Schema**:
```json
{
  "request_id": "req_007",
  "csv_path": "C:\\workspace\\sheet_config.csv"
}
```

**Output Schema**:
```json
{
  "file_path": "C:\\workspace\\export.pdf",
  "status": "success"
}
```

### revit.export_dwg_by_sheet_set

**Purpose**: Export sheets to DWG format

**Input Schema**: Same as PDF export

**Output Schema**:
```json
{
  "file_path": "C:\\workspace\\export.dwg",
  "status": "success"
}
```

### revit.export_ifc_named_setup

**Purpose**: Export model to IFC using named export configuration

**Input Schema**:
```json
{
  "request_id": "req_008",
  "csv_path": "C:\\workspace\\ifc_config.csv"
}
```

**Output Schema**:
```json
{
  "file_path": "C:\\workspace\\setup.ifc",
  "status": "success"
}
```

### revit.export_report

**Purpose**: Generate comprehensive export summary report

**Input Schema**: Standard audit input

**Output Schema**: Standard audit output

---

## Sheet Automation

### revit.batch_create_sheets_from_csv

**Purpose**: Create multiple sheets from CSV specification

**Input Schema**:
```json
{
  "request_id": "req_009",
  "csv_path": "C:\\workspace\\sheets.csv"
}
```

CSV format:
```csv
sheet_number,sheet_name,titleblock
A101,Floor Plan Level 1,A0 Titleblock
A102,Floor Plan Level 2,A0 Titleblock
```

**Output Schema**:
```json
{
  "sheets_created": 3
}
```

### revit.batch_place_views_on_sheets

**Purpose**: Automatically place views on sheets

**Input Schema**: Standard audit input

**Output Schema**: Standard audit output

### revit.titleblock_fill_from_csv

**Purpose**: Populate titleblock parameters from CSV data

**Input Schema**: Standard audit input

**Output Schema**: Standard audit output

### revit.create_print_set

**Purpose**: Create a print set (collection of sheets)

**Input Schema**: Standard audit input

**Output Schema**: Standard audit output

---

## Baseline Tracking

### revit.baseline_export

**Purpose**: Export model state snapshot for comparison

**Input Schema**:
```json
{
  "request_id": "req_010",
  "output_path": "C:\\workspace\\baseline.json"
}
```

**Output Schema**:
```json
{
  "snapshot_id": "baseline-2025-01-07T10:30:00",
  "output_path": "C:\\workspace\\baseline.json"
}
```

**Example**:
```json
// Request
{
  "tool": "revit.baseline_export",
  "payload": {
    "request_id": "baseline_001",
    "output_path": "C:\\workspace\\baseline_v1.json"
  }
}

// Response
{
  "snapshot_id": "baseline-2025-01-07T14:22:33.123456",
  "output_path": "C:\\workspace\\baseline_v1.json"
}
```

### revit.baseline_diff

**Purpose**: Compare two baseline snapshots and report differences

**Input Schema**:
```json
{
  "request_id": "req_011",
  "baseline_a": "C:\\workspace\\baseline_v1.json",
  "baseline_b": "C:\\workspace\\baseline_v2.json"
}
```

**Output Schema**:
```json
{
  "differences": [
    "10 elements added",
    "5 parameters changed",
    "2 views deleted"
  ]
}
```

---

## Package Builder

### revit.publish_package_builder

**Purpose**: Generate Revit package (.rfa, .addin, or custom package) for distribution

**Input Schema**: Standard audit input

**Output Schema**: Standard audit output

---

## Common Patterns

### Request IDs
All tools require a `request_id` field for audit log correlation. Use unique identifiers:
```json
{
  "request_id": "workflow_001_step_02"
}
```

### File Paths
All file paths must:
- Be absolute paths (not relative)
- Fall within configured `allowed_directories`
- Use forward slashes or escaped backslashes: `C:/workspace` or `C:\\workspace`

Invalid paths raise `WorkspaceViolation` errors.

### Error Handling
Failed tool invocations return error responses:
```json
{
  "error": "WorkspaceViolation",
  "message": "Path outside allowed directories: C:\\system32\\file.txt"
}
```

Common errors:
- `WorkspaceViolation`: File path outside sandbox
- `SchemaValidationError`: Invalid input format
- `BridgeError`: Bridge communication failure
- `RevitMCPError`: General tool execution error

### Mock vs Bridge Mode

In **mock mode**, tools return deterministic stub data without Revit:
```json
{
  "status": "healthy",
  "message": "Bridge ready"
}
```

In **bridge mode**, tools execute real Revit API operations:
```json
{
  "status": "healthy",
  "revit_version": "2024",
  "message": "Connected to Revit 2024"
}
```

---

## Full Tool List Summary

| Tool | Category | Purpose |
|------|----------|---------|
| `revit.health` | Health | Check bridge status |
| `revit.open_document` | Document | Open Revit file |
| `revit.list_views` | Document | List all views |
| `revit.model_health_summary` | QA | Overall health report |
| `revit.warning_triage_report` | QA | Categorize warnings |
| `revit.naming_standards_audit` | QA | Validate naming |
| `revit.parameter_compliance_audit` | QA | Check parameters |
| `revit.shared_parameter_binding_audit` | QA | Audit shared params |
| `revit.view_template_compliance_check` | QA | View template audit |
| `revit.tag_coverage_audit` | QA | Untagged elements |
| `revit.room_space_completeness_report` | QA | Room/space data |
| `revit.link_monitor_report` | QA | Linked file audit |
| `revit.coordinate_sanity_check` | QA | Coordinate validation |
| `revit.export_schedules` | Export | Export schedules to CSV |
| `revit.export_quantities` | Export | Export quantities to CSV |
| `revit.export_pdf_by_sheet_set` | Export | Export sheets to PDF |
| `revit.export_dwg_by_sheet_set` | Export | Export sheets to DWG |
| `revit.export_ifc_named_setup` | Export | Export model to IFC |
| `revit.export_report` | Export | Export summary report |
| `revit.baseline_export` | Baseline | Create snapshot |
| `revit.baseline_diff` | Baseline | Compare snapshots |
| `revit.batch_create_sheets_from_csv` | Sheet | Create sheets from CSV |
| `revit.batch_place_views_on_sheets` | Sheet | Place views on sheets |
| `revit.titleblock_fill_from_csv` | Sheet | Fill titleblocks from CSV |
| `revit.create_print_set` | Sheet | Create print set |
| `revit.publish_package_builder` | Package | Build distribution package |

---

## Schema Reference

All schemas are defined in [schemas.py](../packages/mcp-server-revit/src/revit_mcp_server/schemas.py) using Pydantic models.

Tool handler implementations are in [handlers.py](../packages/mcp-server-revit/src/revit_mcp_server/tools/handlers.py).

For integration examples, see [demo.py](../packages/client-demo/demo.py).
