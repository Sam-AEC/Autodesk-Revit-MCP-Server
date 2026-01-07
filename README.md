<div align="center">

<img src="https://raw.githubusercontent.com/modelcontextprotocol/docs/main/logo/light.svg" alt="MCP Logo" width="120"/>

# RevitMCP: Model Context Protocol for Autodesk Revit

**Production-grade MCP server enabling AI agents and automation tools to control Autodesk Revit**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![.NET Framework 4.8](https://img.shields.io/badge/.NET-4.8-512BD4?style=flat-square&logo=dotnet)](https://dotnet.microsoft.com/)
[![Revit 2024-2025](https://img.shields.io/badge/Revit-2024--2025-0696D7?style=flat-square)](https://www.autodesk.com/products/revit)

[Quick Start](#quick-start) • [Features](#features) • [Architecture](#architecture) • [Copilot Integration](#microsoft-copilot-studio-integration) • [Docs](#documentation)

</div>

---

## What is RevitMCP?

RevitMCP bridges the [Model Context Protocol](https://modelcontextprotocol.io) with Autodesk Revit, enabling:

- **Microsoft Copilot Studio** integration for conversational Revit control
- **AI-powered** model analysis, quality assurance, and reporting
- **Batch automation** for exports, audits, and data extraction
- **Secure-by-default** localhost-only bridge with enterprise HTTPS/OAuth options

### Key Features

✅ **25 Revit Tools** - Document management, export (PDF/IFC/DWG/CSV), QA audits, batch operations
✅ **Enterprise Ready** - MSI installer, OAuth2, audit logging, workspace sandboxing
✅ **Copilot Studio** - Pre-built integration guide for Microsoft 365
✅ **Dual Mode** - Mock mode for CI/testing, bridge mode for live Revit
✅ **Production Threading** - ExternalEvent queue with proper Revit main thread execution
✅ **Security First** - Localhost-only by default, path validation, structured audit logs

---

## Quick Start

### Installation (Windows)

**Download the installer:**

1. Go to [Releases](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/releases)
2. Download `RevitMCP-1.0.0.zip`
3. Extract and run:

```powershell
.\install.ps1 -RevitVersion 2024
```

**Or install from source:**

```powershell
git clone https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server.git
cd Autodesk-Revit-MCP-Server
.\scripts\build-addin.ps1 -RevitVersion 2024
.\scripts\install.ps1 -RevitVersion 2024
```

### Verify Installation

1. **Start Revit 2024**
2. **Check bridge health:**
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

3. **Run MCP server:**
   ```powershell
   # Install Python package
   pip install -e packages/mcp-server-revit

   # Start server
   python -m revit_mcp_server
   ```

### Test a Tool

```powershell
# List all views in active document
curl -X POST http://localhost:3000/execute `
  -H "Content-Type: application/json" `
  -d '{"tool":"revit.list_views","payload":{},"request_id":"test1"}'
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ CLIENT LAYER                                            │
│  • Microsoft Copilot Studio                             │
│  • Python scripts                                       │
│  • Custom MCP clients                                   │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS/JSON
          ┌──────────▼──────────┐
          │ MCP Server (Python) │
          │  - Request routing  │
          │  - Security/audit   │
          │  - Workspace guard  │
          └──────────┬──────────┘
                     │ HTTP localhost:3000
          ┌──────────▼──────────┐
          │ Bridge Add-in (C#)  │
          │  - HTTP server      │
          │  - CommandQueue     │
          │  - ExternalEvent    │
          └──────────┬──────────┘
                     │ Revit API
          ┌──────────▼──────────┐
          │ Revit 2024/2025     │
          │  - Active document  │
          │  - Views/elements   │
          │  - Export engines   │
          └─────────────────────┘
```

**Threading Model:**
1. HTTP request arrives → Background thread (BridgeServer)
2. Request queued → CommandQueue (thread-safe)
3. ExternalEvent raised → Revit main thread
4. Command executed → Revit API calls
5. Response returned → TaskCompletionSource correlation
6. HTTP response → Client receives result

---

## Available Tools

### Core Operations
- `revit.health` - Check Revit session status
- `revit.open_document` - Open Revit file
- `revit.list_views` - Enumerate views with metadata

### Exports
- `revit.export_schedules` - Export schedules to CSV
- `revit.export_pdf_by_sheet_set` - Generate PDF from sheets
- `revit.export_dwg_by_sheet_set` - Export DWG drawings
- `revit.export_ifc_named_setup` - Export IFC using predefined setup

### Quality Assurance (15 Audit Tools)
- `revit.model_health_summary` - Overall model health report
- `revit.warning_triage_report` - Categorize Revit warnings
- `revit.naming_standards_audit` - Validate naming conventions
- `revit.parameter_compliance_audit` - Check parameter completeness
- `revit.view_template_compliance_check` - Ensure template usage
- `revit.tag_coverage_audit` - Verify tag placement
- `revit.link_monitor_report` - Monitor linked files
- ...and 8 more (see [API Reference](docs/api.md))

### Batch Operations
- `revit.batch_create_sheets_from_csv` - Create sheets from CSV
- `revit.titleblock_fill_from_csv` - Populate titleblock data
- `revit.batch_place_views_on_sheets` - Auto-place views

---

## Microsoft Copilot Studio Integration

RevitMCP integrates with Microsoft Copilot Studio to enable conversational Revit control.

### Architecture

Since Revit is a desktop app, we use an **on-prem worker** model:

```
[User in Teams] → [Copilot Studio] → [MCP Server (Azure)]
                                           ↓
                                    [Azure Queue]
                                           ↓
                        [On-prem Worker] → [Revit + Bridge]
```

### Quick Setup

1. **Deploy MCP Server to Azure:**
   ```bash
   az containerapp create --name revit-mcp-server \
     --image ghcr.io/sam-aec/revit-mcp-server:latest \
     --ingress external --target-port 8000
   ```

2. **Configure Entra ID** (OAuth2 tokens)

3. **Deploy on-prem worker** (polls Azure queue, executes in Revit)

4. **Add to Copilot Studio:**
   - Create agent: "Revit Assistant"
   - Add MCP server URL with OAuth
   - Select tools: `revit.health`, `revit.list_views`, `revit.export_schedules`
   - Publish to Teams

**Full guide:** [docs/copilot-integration.md](docs/copilot-integration.md)

---

## Security

### Default: Localhost Only

Out of the box:
- Bridge binds to `127.0.0.1:3000` (loopback only)
- **Zero network exposure**
- All file paths validated against workspace allowlist

### Enterprise Mode (Opt-in)

For Copilot or remote access:
- ✅ HTTPS via IIS/nginx reverse proxy
- ✅ OAuth2 JWT validation (Entra ID)
- ✅ Tenant allowlist
- ✅ Rate limiting (100 req/min)
- ✅ JSONL audit logs with caller identity

**Threat model:** [docs/security.md](docs/security.md)

---

## Development

### Build from Source

```powershell
# Build C# add-in
.\scripts\build-addin.ps1 -RevitVersion 2024

# Run Python tests
cd packages/mcp-server-revit
pytest tests/ -v --cov

# Package distribution
.\scripts\package.ps1 -Version 1.0.0
```

### Project Structure

```
mcp/
├── packages/
│   ├── mcp-server-revit/        # Python MCP server
│   │   ├── src/revit_mcp_server/
│   │   │   ├── server.py        # Main server
│   │   │   ├── bridge/client.py # HTTP bridge client
│   │   │   ├── security/        # Workspace + audit
│   │   │   └── tools/handlers.py# 25 tool handlers
│   │   └── tests/               # Pytest suite
│   │
│   └── revit-bridge-addin/      # C# Revit add-in
│       ├── src/Bridge/
│       │   ├── App.cs           # IExternalApplication
│       │   ├── BridgeServer.cs  # HTTP server
│       │   ├── CommandQueue.cs  # Request queue
│       │   └── BridgeCommandFactory.cs # Tool executor
│       └── RevitBridge.csproj
│
├── scripts/
│   ├── build-addin.ps1          # Build C# DLL
│   ├── package.ps1              # Create dist/
│   └── install.ps1              # Install to Revit
│
├── docs/
│   ├── copilot-integration.md   # Copilot Studio guide
│   ├── security.md              # Security model
│   └── api.md                   # Tool reference
│
└── .github/workflows/build.yml  # CI/CD
```

---

## Documentation

- **[Admin Guide](docs/admin-guide.md)** - Enterprise deployment, silent install, troubleshooting
- **[Copilot Integration](docs/copilot-integration.md)** - Step-by-step Copilot Studio setup
- **[Security Model](docs/security.md)** - Threat analysis, hardening, enterprise controls
- **[API Reference](docs/api.md)** - All 25 tools with schemas
- **[Architecture](docs/architecture.md)** - Threading model, request flow

---

## Contributing

Contributions welcome! Please:
1. Fork the repo
2. Create a feature branch
3. Add tests for new tools
4. Run `pytest` and `ruff check`
5. Submit a pull request

---

## License

MIT License - see [LICENSE](LICENSE)

---

## Support

- **Issues:** [GitHub Issues](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues)
- **Security:** See [SECURITY.md](SECURITY.md) for responsible disclosure
- **Discussions:** [GitHub Discussions](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/discussions)

---

<div align="center">

**Built with ❤️ for the AEC community**

[⬆ Back to Top](#revitmcp-model-context-protocol-for-autodesk-revit)

</div>
