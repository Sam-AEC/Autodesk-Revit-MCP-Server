<div align="center">
 
# 🏗️ RevitMCP
 
<!-- Logos -->
<p>
   <img src="https://cdn.simpleicons.org/autodeskrevit/0696D7" alt="Autodesk Revit" height="40" style="margin-right:15px;"/>
   <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Microsoft_logo.svg/2048px-Microsoft_logo.svg.png" alt="Microsoft" height="40" style="margin-right:15px;"/>
   <img src="https://cdn.simpleicons.org/python/3776AB" alt="Python" height="40" style="margin-right:15px;"/>
   <img src="https://cdn.simpleicons.org/dotnet/512BD4" alt=".NET" height="40"/>
</p>

# 🏗️ RevitMCP: AI-Powered Revit Automation

### **Production-grade MCP server enabling AI agents to control Autodesk Revit**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![.NET Framework 4.8](https://img.shields.io/badge/.NET-4.8-512BD4?style=for-the-badge&logo=dotnet)](https://dotnet.microsoft.com/)
[![Revit 2024-2025](https://img.shields.io/badge/Revit-2024--2025-0696D7?style=for-the-badge)](https://www.autodesk.com/products/revit)

[![Tools](https://img.shields.io/badge/Tools-10k+-00D084?style=for-the-badge&logo=revit)](docs/tools.md)
[![Build](https://img.shields.io/badge/Build-Passing-success?style=for-the-badge&logo=github-actions)](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](CONTRIBUTING.md)
[![GitHub Stars](https://img.shields.io/github/stars/Sam-AEC/Autodesk-Revit-MCP-Server?style=for-the-badge&logo=github)](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/stargazers)

[🚀 Quick Start](#quick-start) • [✨ Features](#features) • [🏛️ Architecture](#architecture) • [🤖 Copilot Integration](#microsoft-copilot-studio-integration) • [📚 Docs](#documentation)

</div>

---

## 🎯 What is RevitMCP?

RevitMCP bridges the [Model Context Protocol](https://modelcontextprotocol.io) with Autodesk Revit, enabling:

- **Microsoft Copilot Studio** integration for conversational Revit control
- **AI-powered** model analysis, quality assurance, and reporting
- **Batch automation** for exports, audits, and data extraction
- **Secure-by-default** localhost-only bridge with enterprise HTTPS/OAuth options

> **🎉 Latest Update:** Now with **10,000+ tools** (Universal Bridge) - Unlocking the ENTIRE Revit API (Structure, MEP, Site, Analysis)!
> 
> **🚀 Roadmap:** "God Mode" enabled. Build Villas, Skyscrapers, and run Carbon Analysis via pure prompts.

### ✨ Key Features

<table>
<tr>
<td width="50%">

#### 🛠️ **10,000+ Revit Tools (Universal)**
- **Universal Bridge**: Call ANY API method dynamically
- **Full Coverage**: Site, Rebar, Energy, Carbon Analysis
- **Geometry**: Create complex curves, solids, and analytical models
- **Documentation**: Automate 100% of sheet/view creation

</td>
<td width="50%">

#### 🚀 **Enterprise Ready**
- Production-grade threading model
- OAuth2 & audit logging
- Workspace sandboxing
- Multi-version support (2024/2025)
- CI/CD pipeline included
- Mock mode for testing

</td>
</tr>
<tr>
<td width="50%">

#### 🤖 **AI Integration**
- Microsoft Copilot Studio ready
- Claude Desktop compatible
- Natural language control
- Conversational Revit automation
- Pre-built integration guides

</td>
<td width="50%">

#### 🔒 **Security First**
- Localhost-only by default
- Path validation & sanitization
- Structured JSONL audit logs
- Enterprise HTTPS/OAuth options
- Workspace allowlisting

</td>
</tr>
</table>

---

## 🚀 Quick Start

### 📦 Installation (Windows)

**Option 1: Download the installer**

1. Go to [Releases](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/releases)
2. Download `RevitMCP-1.0.0.zip`
3. Extract and run:

```powershell
.\scripts\install.ps1 -RevitVersion 2024
```

**Option 2: Install from source**

```powershell
git clone https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server.git
cd Autodesk-Revit-MCP-Server
.\scripts\build-addin.ps1 -RevitVersion 2024
.\scripts\install.ps1 -RevitVersion 2024
```

### ✅ Verify Installation

**1. Start Revit 2024**

**2. Check bridge health:**
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

**3. Run MCP server:**
```powershell
# Install Python package
pip install -e packages/mcp-server-revit

# Start server
python -m revit_mcp_server
```

### 🧪 Test a Tool

```powershell
# List all views in active document
curl -X POST http://localhost:3000/execute `
  -H "Content-Type: application/json" `
  -d '{"tool":"revit.list_views","payload":{},"request_id":"test1"}'
```

---

## 🤖 Claude Desktop Integration (Recommended)

**Control Revit with Natural Language!** The easiest way to use RevitMCP is through Claude Desktop.

### Quick Setup

**1. Install Claude Desktop**
- Download from: https://claude.ai/download

**2. Configure MCP Server**

Run the automated setup script:
```powershell
.\setup-claude-desktop.ps1
```

Or manually create/edit: `%APPDATA%\Claude\claude_desktop_config.json`
```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": ["-m", "revit_mcp_server.mcp_server"],
      "env": {
        "MCP_REVIT_WORKSPACE_DIR": "C:\\Users\\YourName\\Documents",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\Users\\YourName\\Documents",
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
        "MCP_REVIT_MODE": "bridge"
      }
    }
  }
}
```

**3. Restart Claude Desktop**
- Completely close Claude Desktop (use Task Manager if needed)
- Reopen Claude Desktop
- Look for "revit" in Settings → Developer → Local MCP servers

**4. Start Using Natural Language!**

With Revit open, try these commands in Claude Desktop:

```
"Create a 30ft by 25ft house with 10ft tall walls on level L1"
```

```
"Show me all the walls in the current project"
```

```
"Build a two-story commercial building, 50x40 feet, with 15ft tall walls"
```

Claude understands your intent and executes the appropriate Revit commands!

### What You Can Say

- **Create**: "Create a rectangular building 60ft by 40ft"
- **Query**: "How many walls are in the project?"
- **Modify**: "Add interior walls to divide the space into 4 rooms"
- **Complex**: "Build a house with a living room, kitchen, and 3 bedrooms"
- **Export**: "Export a PDF of all floor plans"

**Full Guide**: See [CLAUDE_DESKTOP_SETUP.md](CLAUDE_DESKTOP_SETUP.md) for detailed instructions.

---

## 🎬 Demo: Natural Language Control with Claude Desktop

<p align="center">
   <img src="assets/demo.gif" alt="RevitMCP with Claude Desktop - Natural Language Control" width="900"/>
</p>

> **Control Revit with natural language through Claude Desktop!** Just describe what you want to build, and Claude will create it in Revit using the MCP protocol.

## 🏛️ Architecture

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
