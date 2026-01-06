<div align="center">

# 🏗️ Revit MCP Bridge

**Control Autodesk Revit from AI agents, Python scripts, or any MCP client**

<br/>

<p align="center">
  <img src="https://cdn.worldvectorlogo.com/logos/autodesk-revit.svg" alt="Revit" height="60"/>
  &nbsp;&nbsp;&nbsp;
  <span style="font-size: 2em;">→</span>
  &nbsp;&nbsp;&nbsp;
  <img src="https://www.vectorlogo.zone/logos/python/python-icon.svg" alt="Python" height="60"/>
  &nbsp;&nbsp;&nbsp;
  <img src="https://cdn.worldvectorlogo.com/logos/c--4.svg" alt="C#" height="60"/>
</p>

<br/>

[![Build](https://img.shields.io/github/actions/workflow/status/Sam-AEC/mcp/ci.yml?style=for-the-badge&logo=github)](https://github.com/Sam-AEC/mcp/actions)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Revit](https://img.shields.io/badge/Revit-2020--2024-0696D7?style=for-the-badge&logo=autodesk)](https://autodesk.com/revit)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![.NET](https://img.shields.io/badge/.NET-4.8-512BD4?style=for-the-badge&logo=dotnet)](https://dotnet.microsoft.com)

</div>

---

## What It Does

Exposes **25 Revit operations** through the Model Context Protocol. Use it with:
- 🤖 AI agents (Claude, ChatGPT, custom tools)
- 🐍 Python/TypeScript automation
- 🔄 CI/CD pipelines
- ☁️ Cloud workflows

**Components:**
- **MCP Server** (Python) → Validates requests, enforces sandboxing, logs everything
- **Bridge Add-in** (C# .NET) → Runs inside Revit, executes API calls via ExternalEvent
- **Mock Mode** → Test without Revit (perfect for CI)

---

## Quick Start

### Mock Mode (No Revit Required)

```bash
git clone https://github.com/Sam-AEC/mcp.git && cd mcp
python -m venv venv && source venv/bin/activate
pip install -e packages/mcp-server-revit[dev]

export MCP_REVIT_MODE=mock WORKSPACE_DIR="$(pwd)/workspace"
mkdir -p workspace && pytest packages/mcp-server-revit/tests -v

python -m revit_mcp_server  # Terminal 1
python packages/client-demo/demo.py  # Terminal 2
```

### Bridge Mode (Windows + Revit)

```powershell
# After mock setup above...
$env:REVIT_SDK = "C:\Program Files\Autodesk\Revit 2024\SDK"
.\scripts\build-addin.ps1
.\scripts\install-addin.ps1 -RevitYear 2024

# Start Revit, then:
$env:MCP_REVIT_MODE = "bridge"
python -m revit_mcp_server
```

---

## Tools (25)

| Category | Tools |
|----------|-------|
| **Health** | `revit.health` |
| **Documents** | `open_document`, `list_views` |
| **QA Audits** | `model_health_summary`, `warning_triage`, `naming_standards`, `parameter_compliance`, `shared_params`, `view_templates`, `tag_coverage`, `room_completeness`, `link_monitor`, `coordinate_check` |
| **Exports** | `schedules`, `quantities`, `pdf`, `dwg`, `ifc` |
| **Sheets** | `batch_create`, `place_views`, `titleblock_fill` |
| **Baseline** | `export`, `diff` |

[Full docs →](docs/tools.md)

---

## Example: AI QA Agent

```python
# Agent checks Revit model for issues
response = client.call_tool("revit.open_document", {
    "file_path": "/workspace/hospital.rvt"
})

warnings = client.call_tool("revit.warning_triage_report", {})
# → {"issues_found": 42, "severity": "warning"}

naming = client.call_tool("revit.naming_standards_audit", {})
# → Agent generates report with fixes
```

---

## Architecture

```
AI Agent/Script
    ↓ (MCP stdio)
Python Server (validation, sandboxing, logging)
    ↓ (HTTP localhost:3000)
C# Bridge Add-in (ExternalEvent queue)
    ↓ (Revit API)
Autodesk Revit
```

**Why?** Revit API needs .NET + Windows + UI thread. This bridge handles complexity while exposing simple JSON tools.

[Architecture docs →](docs/architecture.md)

---

## Security

✅ Workspace sandboxing (paths validated)
✅ Schema validation (Pydantic)
✅ Audit logs (JSONL with timestamps)
✅ Mock mode (CI without Revit)
✅ localhost-only (no external exposure)

[Security docs →](docs/security.md)

---

## Use Cases

**Automated QA** → Run naming/parameter checks on every commit
**Scheduled Exports** → Nightly schedule/quantity exports to shared drives
**AI Workflows** → Let agents analyze models and suggest fixes
**Baseline Tracking** → Compare model snapshots over time

---

## Roadmap

**Next (v0.2):** Real Revit API calls (currently stubs), async HTTP, error handling
**Later:** More QA tools, Dynamo integration, Navisworks export, BIM 360 support

---

## Docs

[Install](docs/install.md) • [Tools](docs/tools.md) • [Architecture](docs/architecture.md) • [Security](docs/security.md) • [Contributing](CONTRIBUTING.md)

---

## License

MIT • Built with [mcp-use](https://github.com/mcp-use/mcp-use) framework

<div align="center">

⭐ **Star if useful** • [Report Bug](https://github.com/Sam-AEC/mcp/issues) • [Request Feature](https://github.com/Sam-AEC/mcp/issues)

</div>
