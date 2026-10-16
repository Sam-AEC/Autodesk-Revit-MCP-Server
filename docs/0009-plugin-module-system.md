# ADR 0009: Plugin Module System

## Status
Accepted

## Context
AEC Model Bridge contains a large set of tools (over 270) spanning multiple software hosts (Revit, Rhino, Navisworks) and workflows (QA/QC, massing, parameters). Hardcoding these into a single monolithic server makes the code brittle, degrades LLM tool selection performance, and prevents firms from writing custom company-standard checking rules. We need a modular plugin system that encapsulates commands, schemas, UI files, and QA rules.

## Decisions

### 1. Module Packaging & Discovery
A **Module** is a folder containing a manifest (`module.json`), code entry points (`module.py`), validation rules, and optional HTML cards. The **ModuleRegistry** loads them from three sources:
1. **Built-in**: Packaged within the hub wheel (`revit_mcp_server/modules/<name>/`).
2. **User/Firm Folder**: Local configuration directory (`%LOCALAPPDATA%\AECModelBridge\modules\<name>\`).
3. **Python Entry Points**: Discovered dynamically via `[project.entry-points."aec_model_bridge.modules"]` in installed packages.

### 2. Module Manifest Schema (`module.json`)
Every module must ship a schema-compliant manifest:
```json
{
  "id": "qaqc_checker",
  "name": "QA/QC Checker",
  "version": "1.0.0",
  "schema_version": 1,
  "min_hub_version": "1.2.0",
  "requires_providers": ["revit", "graph"],
  "requires_tools": ["revit_get_warnings"],
  "permissions": ["model.read", "workspace.write"],
  "commands": [
    {
      "id": "run_health_check",
      "title": "Run Health Check",
      "surface": ["ribbon", "panel", "mcp"],
      "mcp_tool": "qaqc_run_health_check",
      "execution_mode": "async",
      "is_mutating": false,
      "input_schema": {
        "type": "object",
        "properties": {
          "ruleset": {"type": "string", "default": "core"}
        }
      }
    }
  ],
  "ui": {
    "panel_card": "ui/findings_card.html"
  },
  "hooks": {
    "validate": "module:QaqcModule.validate"
  }
}
```

### 3. Enforced Security Permissions
Permissions are declared in the manifest and enforced by the hub at dispatch time:
- `model.read`: Grants read-only access to elements/properties.
- `model.write`: Permits modifications (requires approval gate).
- `model.delete`: Permits destructive actions (requires explicit confirmation).
- `workspace.write`: Restricted file output within the sandboxed workspace.
- `net.local`: Inter-app communication on local loopback.
- `net.cloud`: External synchronization (Speckle, ACC).
- `python.host`: Raw execution access (off by default, requires expert profile).

### 4. Manifest Exposure & MCP Mapping
- **To Panel**: The dockable UI queries `module_list_commands` and renders cards or panel buttons.
- **To MCP Client**: Every command with `"mcp"` surface is registered dynamically as an MCP tool named `<module_id>_<command_id>`. Schema and metadata properties (`is_mutating`, `destructive`) are carried over.

### 5. Execution Validation & Lifecycle Hooks
- **Schema Validation**: All inputs and outputs are validated against the manifest's `input_schema` and `output_schema` before execution.
- **Validate Hook**: Custom pre-execution logic runs at planning time (e.g., checks against company naming conventions). Can return warning or blocker lists.
- **On Result Hook**: Post-execution hooks run for audit ledger updates, database syncing, or notifications.

## Consequences
- **Extensibility**: Non-programmers can configure rule sets via YAML, while developers can distribute packaged python modules.
- **Tool-Context Efficiency**: LLMs are exposed to namespace-grouped tools, preventing tool list exhaustion.
- **Safety Allowlist**: Firms can deploy customized manifests restricting network and Python execution access.
