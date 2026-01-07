<div align="center">

<img src="https://cdn.simpleicons.org/autodeskrevit/0696D7" alt="Revit" height="80"/>

# Revit MCP Server

**Model Context Protocol server for Autodesk Revit**

[![License: MIT](https://img.shields.io/badge/License-MIT-0078D4?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![.NET](https://img.shields.io/badge/.NET-4.8-512BD4?style=flat-square&logo=dotnet)](https://dotnet.microsoft.com)
[![Revit](https://img.shields.io/badge/Revit-2024%20%7C%202025-0696D7?style=flat-square)](https://autodesk.com/products/revit)

[Quick Start](#quick-start) · [Documentation](docs/) · [API Reference](docs/tools.md)

</div>

---

## Overview

Production-ready MCP server enabling AI agents to control Autodesk Revit through natural language. Integrates with Claude Desktop, Microsoft Copilot, and custom MCP clients.

**Key Features:**
- 105+ Revit API tools (geometry, views, sheets, families)
- Localhost-only bridge with <100ms latency
- Thread-safe ExternalEvent architecture
- OAuth2 and audit logging support

---

## Quick Start

### Prerequisites

- Windows 10/11
- Autodesk Revit 2024 or 2025
- Python 3.11+
- .NET Framework 4.8

### Installation

```powershell
# Clone repository
git clone https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server.git
cd Autodesk-Revit-MCP-Server

# Build Revit add-in
.\scripts\build-addin.ps1 -RevitVersion 2024

# Install Python package
pip install -e packages/mcp-server-revit
```

### Configure Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": ["-m", "revit_mcp_server.mcp_server"],
      "env": {
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
        "MCP_REVIT_MODE": "bridge"
      }
    }
  }
}
```

### Verify Installation

Start Revit, then:

```powershell
curl http://localhost:3000/health
```

Expected response:
```json
{
  "status": "healthy",
  "revit_version": "2024"
}
```

---

## Architecture

```
┌─────────────────────────────────┐
│ AI Client (Claude/Copilot)     │
└───────────────┬─────────────────┘
                │ MCP Protocol
┌───────────────▼─────────────────┐
│ MCP Server (Python)             │
│ - Tool Registry                 │
│ - Security/Audit                │
└───────────────┬─────────────────┘
                │ HTTP :3000
┌───────────────▼─────────────────┐
│ Revit Bridge Add-in (C#)        │
│ - HTTP Server                   │
│ - ExternalEvent Handler         │
└───────────────┬─────────────────┘
                │ Revit API
┌───────────────▼─────────────────┐
│ Autodesk Revit 2024/2025        │
└─────────────────────────────────┘
```

**Threading Model:** HTTP requests are queued and executed on Revit's main thread via `ExternalEvent` for thread safety.

---

## Available Tools

### Document Management
- `revit.create_new_document` - Create blank project
- `revit.open_document` - Open RVT/RFA file
- `revit.save_document` - Save active document
- `revit.get_document_info` - Get project metadata

### Geometry
- `revit.create_wall` - Create wall
- `revit.create_floor` - Create floor
- `revit.create_roof` - Create roof
- `revit.create_ceiling` - Create ceiling
- `revit.create_door` - Place door
- `revit.create_window` - Place window
- `revit.create_column` - Create column
- `revit.create_beam` - Create beam
- `revit.create_room` - Create room

### Levels & Views
- `revit.create_level` - Create level
- `revit.list_levels` - List all levels
- `revit.create_floor_plan` - Create floor plan view
- `revit.create_section_view` - Create section view
- `revit.create_3d_view` - Create 3D view
- `revit.list_views` - List all views

### Sheets & Documentation
- `revit.create_sheet` - Create sheet
- `revit.list_sheets` - List all sheets
- `revit.place_view_on_sheet` - Place view on sheet

### Elements
- `revit.get_elements` - Query elements
- `revit.get_element_properties` - Get parameters
- `revit.set_element_properties` - Update parameters
- `revit.delete_elements` - Delete elements

### Families
- `revit.load_family` - Load family from RFA
- `revit.list_families` - List loaded families
- `revit.place_family_instance` - Place instance

### Export
- `revit.export_pdf` - Export to PDF
- `revit.export_dwg` - Export to DWG
- `revit.export_ifc` - Export to IFC
- `revit.export_nwc` - Export to Navisworks

**Full API Reference:** [docs/tools.md](docs/tools.md)

---

## Security

**Default:** Localhost-only (`127.0.0.1:3000`), no authentication required.

**Enterprise:** Optional HTTPS, OAuth2 (Entra ID), audit logging, and rate limiting.

See [docs/security.md](docs/security.md) for details.

---

## Project Structure

```
Autodesk-Revit-MCP-Server/
├── packages/
│   ├── revit-bridge-addin/       # C# Revit Add-in
│   │   └── src/Bridge/
│   │       ├── App.cs            # IExternalApplication
│   │       ├── BridgeServer.cs   # HTTP server
│   │       └── BridgeCommandFactory.cs
│   └── mcp-server-revit/         # Python MCP Server
│       ├── src/revit_mcp_server/
│       │   ├── mcp_server.py     # MCP protocol
│       │   ├── bridge/client.py  # HTTP client
│       │   └── tools/            # Tool handlers
│       └── tests/
├── scripts/
│   ├── build-addin.ps1           # Build C# DLL
│   └── install.ps1               # Deploy to Revit
├── docs/
│   ├── tools.md                  # API reference
│   ├── architecture.md           # System design
│   └── security.md               # Security model
└── README.md
```

---

## Documentation

- [Installation Guide](docs/install.md)
- [API Reference](docs/tools.md)
- [Architecture](docs/architecture.md)
- [Security Model](docs/security.md)
- [Claude Desktop Setup](CLAUDE_DESKTOP_SETUP.md)
- [Contributing](CONTRIBUTING.md)

---

## License

[MIT License](LICENSE) - Copyright (c) 2025

---

## Links

- [Issues](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues)
- [Discussions](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/discussions)
- [Changelog](CHANGELOG.md)
- [Model Context Protocol](https://modelcontextprotocol.io)

---

<div align="center">

**[⬆ Back to Top](#revit-mcp-server)**

</div>
