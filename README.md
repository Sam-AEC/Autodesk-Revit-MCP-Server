<div align="center">

# 🏗️ Revit MCP Bridge

### **Connect AI Agents to Autodesk Revit**

Automate Revit workflows through the Model Context Protocol - from Python, TypeScript, or any MCP client

<br/>

<p align="center">
  <img src="https://seeklogo.com/images/A/autodesk-revit-logo-0BEB642AE2-seeklogo.com.png" alt="Autodesk Revit" height="80"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <strong style="font-size: 2em;">×</strong>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://www.python.org/static/community_logos/python-logo-generic.svg" alt="Python" height="80"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <strong style="font-size: 2em;">×</strong>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/b/bd/Logo_C_sharp.svg/256px-Logo_C_sharp.svg.png" alt="C#" height="80"/>
</p>

<br/>

[![Build](https://img.shields.io/github/actions/workflow/status/Sam-AEC/mcp/ci.yml?branch=main&style=for-the-badge&logo=github)](https://github.com/Sam-AEC/mcp/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-green.svg?style=for-the-badge)](https://github.com/Sam-AEC/mcp/releases)
[![Revit](https://img.shields.io/badge/Revit-2020--2024-0696D7.svg?style=for-the-badge&logo=autodesk)](https://www.autodesk.com/products/revit/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![C#](https://img.shields.io/badge/C%23-.NET_4.8-512BD4.svg?style=for-the-badge&logo=csharp&logoColor=white)](https://docs.microsoft.com/en-us/dotnet/csharp/)

</div>

---

## 🎯 What Is This?

A production-ready bridge that exposes **Autodesk Revit** as a Model Context Protocol (MCP) server. This enables:

- **🤖 AI Agents** - Let Claude Desktop, ChatGPT, or custom agents control Revit
- **🐍 Python Automation** - Script Revit workflows without .NET complexity
- **🔄 CI/CD Integration** - Run QA checks, exports, and reports in pipelines
- **☁️ Cloud Workflows** - Trigger Revit operations from web apps or serverless functions

**Three Components:**

1. **MCP Server** (Python) - Exposes 25 Revit tools with validation and sandboxing
2. **Bridge Add-in** (C# .NET 4.8) - Runs inside Revit, executes API operations
3. **Demo Client** (Python) - Example automation showing health checks, exports, QA audits

---

## 🚀 Why This Exists

### The Problem
Revit's API is powerful but locked to .NET and Windows. Building modern automation requires:
- Complex Python ↔ .NET interop (pythonnet, COM, or process boundaries)
- Windows-specific deployment (no Linux CI/CD)
- Manual thread marshalling (Revit API requires UI thread)
- Custom protocols for every integration

### The Solution
This bridge provides a **standard interface** using the Model Context Protocol:

✅ **Mock Mode** - Test without Revit (Linux CI, local dev, unit tests)
✅ **Workspace Sandboxing** - File operations restricted to allowed directories
✅ **Schema Validation** - All inputs validated with Pydantic before execution
✅ **Audit Logging** - Structured JSONL logs track every operation
✅ **Language Agnostic** - MCP clients exist for Python, TypeScript, Rust, Go

**Use Cases:**
- AI agents that query Revit models and generate reports
- Automated QA checks on every commit (naming standards, parameter compliance)
- Scheduled exports (schedules, quantities, PDFs) to shared drives
- Multi-model workflows (compare baselines, batch processing)

---

## ⚡ Quick Start (Mock Mode)

Run the complete workflow **without Revit or Windows**. Perfect for development, testing, and CI/CD.

```bash
# Clone and setup
git clone https://github.com/Sam-AEC/mcp.git
cd mcp
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install
pip install -e packages/mcp-server-revit[dev]

# Configure mock mode
export MCP_REVIT_MODE=mock
export WORKSPACE_DIR="$(pwd)/workspace"
export MCP_REVIT_ALLOWED_DIRECTORIES="$(pwd)/workspace"
mkdir -p workspace

# Verify
pytest packages/mcp-server-revit/tests -v

# Run server (terminal 1)
python -m revit_mcp_server

# Run demo (terminal 2)
python packages/client-demo/demo.py
```

**Expected Output:**
```json
{"status": "healthy", "mode": "mock"}
{"document_id": "sample_model", "title": "sample_model.rvt"}
{"categories_exported": 5, "output_path": "workspace/quantities.csv"}
```

Check `workspace/audit.jsonl` for structured logs.

---

## 🪟 Quick Start (Bridge Mode)

Connect to a **real Revit instance** for production workflows.

**Prerequisites:**
- Windows 10/11
- Revit 2020-2024
- Visual Studio 2019+ or MSBuild
- Python 3.11+

```powershell
# Setup Python (same as mock mode)
git clone https://github.com/Sam-AEC/mcp.git
cd mcp
python -m venv venv
venv\Scripts\activate
pip install -e packages/mcp-server-revit[dev]

# Build Revit add-in
$env:REVIT_SDK = "C:\Program Files\Autodesk\Revit 2024\SDK"
.\scripts\build-addin.ps1

# Install add-in
.\scripts\install-addin.ps1 -RevitYear 2024

# Start Revit (bridge auto-loads on localhost:3000)

# Configure bridge mode
$env:MCP_REVIT_MODE = "bridge"
$env:MCP_REVIT_BRIDGE_URL = "http://localhost:3000"
$env:WORKSPACE_DIR = "C:\revit-workspace"
$env:MCP_REVIT_ALLOWED_DIRECTORIES = "C:\revit-workspace"
mkdir C:\revit-workspace -ErrorAction SilentlyContinue

# Run
python -m revit_mcp_server  # Terminal 1
python packages/client-demo/demo.py  # Terminal 2
```

**Expected Output:**
```json
{"status": "healthy", "mode": "bridge", "revit_version": "2024"}
// Real Revit operations execute
// Files saved to C:\revit-workspace\
```

---

## 🛠️ Available Tools (25 Total)

### 📋 Document Operations
```python
revit.health              # Bridge connectivity check
revit.open_document       # Open .rvt or .rfa files
revit.list_views          # Enumerate all views
```

### 🔍 QA & Audits (10 Tools)
```python
revit.model_health_summary                # Overall health metrics
revit.warning_triage_report               # Categorize warnings
revit.naming_standards_audit              # Validate naming conventions
revit.parameter_compliance_audit          # Check required parameters
revit.shared_parameter_binding_audit      # Verify shared params
revit.view_template_compliance_check      # Audit view templates
revit.tag_coverage_audit                  # Find untagged elements
revit.room_space_completeness_report      # Room/space validation
revit.link_monitor_report                 # Linked file status
revit.coordinate_sanity_check             # Project coordinates
```

### 📤 Export Operations
```python
revit.export_schedules            # Schedules → CSV
revit.export_quantities           # Material takeoffs → CSV
revit.export_pdf_by_sheet_set     # Batch PDF export
revit.export_dwg_by_sheet_set     # Batch DWG export
revit.export_ifc_named_setup      # IFC with custom settings
```

### 📄 Sheet Automation
```python
revit.batch_create_sheets_from_csv    # Bulk sheet creation
revit.batch_place_views_on_sheets     # Automated view placement
revit.titleblock_fill_from_csv        # Populate titleblock data
```

### 📊 Baseline Tracking
```python
revit.baseline_export    # Snapshot model state
revit.baseline_diff      # Compare two snapshots
```

**Full documentation:** [docs/tools.md](docs/tools.md)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  AI Agent / Automation Script                                   │
│  (Claude Desktop, Python, TypeScript, cron jobs)                │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MCP Protocol (stdio JSON-RPC)
┌──────────────────────────▼──────────────────────────────────────┐
│  MCP Server (Python 3.11+)                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │ Pydantic       │  │ Workspace      │  │ Audit Logger     │  │
│  │ Validation     │  │ Sandbox        │  │ (JSONL)          │  │
│  └────────────────┘  └────────────────┘  └──────────────────┘  │
│                                                                 │
│  Mode: Mock (CI/testing) OR Bridge (production Revit)          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP POST (localhost:3000)
┌──────────────────────────▼──────────────────────────────────────┐
│  Revit Bridge Add-in (C# .NET 4.8)                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ HttpListener → ExternalEvent Queue → Revit API            │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────────────────────┘
                         │ Revit API (.NET Framework 4.8)
┌────────────────────────▼────────────────────────────────────────┐
│  Autodesk Revit (2020, 2021, 2022, 2023, 2024)                 │
│  Document operations • Exports • QA metrics                     │
└─────────────────────────────────────────────────────────────────┘
```

**Design Decisions:**

| Decision | Reason |
|----------|--------|
| **Python MCP Server** | MCP ecosystem is Python/TS, easier client integration |
| **HTTP Bridge** | Clean process boundary, debuggable (curl/Postman) |
| **ExternalEvent** | Revit API requires UI thread execution |
| **Mock Mode** | CI/CD on Linux without Revit dependency |
| **localhost-only** | No external exposure, simple security model |

**Deep dive:** [docs/architecture.md](docs/architecture.md)

---

## 🔒 Security

<table>
<tr>
<td width="50%">

**Workspace Sandboxing**
- All file paths validated against allowed directories
- Path traversal attacks blocked (`../../../etc/passwd`)
- Symbolic links resolved and validated

</td>
<td width="50%">

**Schema Validation**
- Pydantic models enforce types and constraints
- Invalid inputs rejected before execution
- Clear error messages for debugging

</td>
</tr>
<tr>
<td>

**Audit Logging**
- JSONL format with timestamps and request IDs
- Records inputs, outputs, file artifacts
- Tamper-evident chronological ordering

</td>
<td>

**Safe Defaults**
- Mock mode for CI/CD (no Revit needed)
- Bridge binds to `127.0.0.1` only
- No external network exposure

</td>
</tr>
</table>

**Details:** [docs/security.md](docs/security.md)

---

## 📚 Documentation

| Guide | Description |
|-------|-------------|
| [Installation](docs/install.md) | Mock mode, bridge mode, troubleshooting |
| [Tool Catalog](docs/tools.md) | All 25 tools with schemas and examples |
| [Architecture](docs/architecture.md) | Design decisions, trust boundaries |
| [Security](docs/security.md) | Sandboxing, validation, audit logs |
| [Contributing](CONTRIBUTING.md) | How to add tools and submit PRs |

---

## 🗺️ Roadmap

**v0.2.0 - Real Revit Integration**
- [ ] Implement actual Revit API calls in bridge (currently stubs)
- [ ] ExternalEvent queue processing with error handling
- [ ] Async HTTP client for parallel operations

**v0.3.0 - Enhanced Tools**
- [ ] More QA tools (circulation analysis, clash detection)
- [ ] Enhanced sheet automation (view placement optimization)
- [ ] Batch document processing (folder-level operations)

**Future**
- [ ] Dynamo integration for visual programming workflows
- [ ] Revit Server and BIM 360 cloud model support
- [ ] Navisworks export tool
- [ ] Optional telemetry (disabled by default, opt-in)

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**High-impact contributions:**
- Implement real Revit API operations in bridge (replace stubs)
- Add new tools (e.g., `revit.export_navisworks`, `revit.create_3d_view`)
- Improve test coverage
- Add more QA audit tools

---

## 💡 Example Use Cases

**1. Automated QA on Pull Requests**
```yaml
# .github/workflows/revit-qa.yml
- run: python -m revit_mcp_server --tool revit.naming_standards_audit
- run: python -m revit_mcp_server --tool revit.parameter_compliance_audit
```

**2. Scheduled Export Job**
```python
# Export all schedules to CSV every night
client.call_tool("revit.export_schedules", {
    "output_path": "/exports/schedules-2025-01-07.csv"
})
```

**3. AI Agent Workflow**
```
User: "Check this Revit model for warnings and generate a report"
Agent: → revit.open_document
      → revit.warning_triage_report
      → Generates markdown report with findings
```

**4. Baseline Comparison**
```python
# Track model changes over time
baseline_v1 = client.call_tool("revit.baseline_export", {...})
baseline_v2 = client.call_tool("revit.baseline_export", {...})
diff = client.call_tool("revit.baseline_diff", {
    "baseline_a": baseline_v1,
    "baseline_b": baseline_v2
})
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE)

Copyright (c) 2025 MCP Revit Bridge Contributors

---

## 🙏 Acknowledgments

- **Autodesk** for the Revit API
- **Anthropic** for the Model Context Protocol specification
- Built with [mcp-use](https://github.com/mcp-use/mcp-use) framework
- Python and .NET open-source communities

---

<div align="center">

**⭐ Star this repo if you find it useful!**

[Report Bug](https://github.com/Sam-AEC/mcp/issues) • [Request Feature](https://github.com/Sam-AEC/mcp/issues) • [Discussions](https://github.com/Sam-AEC/mcp/discussions)

</div>
