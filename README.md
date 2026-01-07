<div align="center">

# Autodesk Revit MCP Server

### **AI-Powered Revit Automation via Model Context Protocol**

<p align="center">
  <img src="https://cdn.simpleicons.org/autodeskrevit/0696D7" alt="Revit" height="50" style="margin:0 10px;"/>
  <img src="https://cdn.simpleicons.org/python/3776AB" alt="Python" height="50" style="margin:0 10px;"/>
  <img src="https://cdn.simpleicons.org/dotnet/512BD4" alt=".NET" height="50" style="margin:0 10px;"/>
  <img src="https://upload.wikimedia.org/wikipedia/commons/1/13/Anthropic_logo.svg" alt="Claude" height="50" style="margin:0 10px;"/>
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![.NET 4.8](https://img.shields.io/badge/.NET-4.8-512BD4?style=for-the-badge&logo=dotnet)](https://dotnet.microsoft.com/)
[![Revit 2024+](https://img.shields.io/badge/Revit-2024--2025-0696D7?style=for-the-badge)](https://www.autodesk.com/products/revit)

[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](CONTRIBUTING.md)
[![GitHub Stars](https://img.shields.io/github/stars/Sam-AEC/Autodesk-Revit-MCP-Server?style=for-the-badge&logo=github)](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/stargazers)

**[Quick Start](#-quick-start)** • **[Features](#-features)** • **[Examples](#-real-world-examples)** • **[Architecture](#-architecture)** • **[Documentation](#-documentation)** • **[Contributing](#-contributing)**

</div>

---

## 🎯 Overview

**Autodesk Revit MCP Server** is a production-ready implementation of the [Model Context Protocol](https://modelcontextprotocol.io) (MCP) that enables AI agents—like Claude, ChatGPT, and Microsoft Copilot—to interact with Autodesk Revit through natural language.

Build buildings by describing them. Audit models by asking questions. Export documentation with a prompt.

### What Makes This Different?

- **🚀 105+ Tools**: Complete Revit API coverage (create walls, floors, roofs, views, sheets, families)
- **🤖 Natural Language Control**: Talk to Revit through Claude Desktop, Microsoft Copilot, or custom AI agents
- **🏗️ Parametric Design**: Build complex structures (towers, villas, stadiums) with AI-generated geometry
- **🔒 Enterprise Security**: Localhost-only by default, with OAuth2 and audit logging for production
- **⚡ Real-Time Bridge**: Sub-100ms latency HTTP bridge for responsive AI interactions
- **🧪 Fully Tested**: Built and validated through real-world projects (houses, towers, The Gherkin)

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🏗️ **Comprehensive Revit Control**

- **Model Creation**: Walls, floors, roofs, doors, windows, rooms
- **Levels & Views**: Create levels, floor plans, sections, 3D views
- **Parametric Design**: Generate complex geometry with AI
- **Families**: Load and place family instances
- **Documentation**: Create sheets, place views, fill titleblocks
- **MEP Systems**: HVAC, plumbing, electrical (basic support)

</td>
<td width="50%" valign="top">

### 🤖 **AI Agent Integration**

- **Claude Desktop**: Ready-to-use natural language interface
- **Microsoft Copilot**: Enterprise conversational AI
- **Custom MCP Clients**: Build your own integrations
- **Tool Discovery**: Auto-exposed capabilities via MCP protocol
- **Streaming Support**: Real-time responses for long operations
- **Context Management**: Maintains conversation state

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔒 **Enterprise-Grade Security**

- **Localhost-Only Default**: Zero network exposure out-of-the-box
- **Workspace Sandboxing**: Path validation against allowlist
- **JSONL Audit Logs**: Structured logging with request correlation
- **OAuth2 Support**: Entra ID integration for enterprise deployments
- **Rate Limiting**: Configurable request throttling
- **HTTPS Ready**: Reverse proxy support for remote access

</td>
<td width="50%" valign="top">

### ⚡ **Performance & Reliability**

- **Sub-100ms Latency**: Fast HTTP bridge with async processing
- **Thread-Safe**: Revit ExternalEvent-based architecture
- **Error Recovery**: Graceful handling of Revit API failures
- **Idempotent Operations**: Safe retry logic
- **Multi-Version**: Supports Revit 2024 and 2025
- **Mock Mode**: Test without Revit installation

</td>
</tr>
</table>

---

## 🚀 Quick Start

### Prerequisites

- **Windows 10/11** (64-bit)
- **Autodesk Revit 2024 or 2025**
- **Python 3.11+**
- **.NET Framework 4.8**
- **Claude Desktop** (optional, for natural language control)

### Installation (5 Minutes)

#### 1. Clone the Repository

```powershell
git clone https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server.git
cd Autodesk-Revit-MCP-Server
```

#### 2. Build the Revit Add-in

```powershell
.\scripts\build-addin.ps1 -RevitVersion 2024
```

This compiles the C# bridge add-in and deploys it to:
```
C:\ProgramData\RevitMCP\bin\RevitBridge.dll
```

#### 3. Install Python Package

```powershell
pip install -e packages/mcp-server-revit
```

#### 4. Verify Installation

**Start Revit 2024**, then test the bridge:

```powershell
curl http://localhost:3000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0.0",
  "revit_version": "2024",
  "active_document": "Project1"
}
```

#### 5. Configure Claude Desktop (Recommended)

Run the setup script:
```powershell
.\setup-claude-desktop.ps1
```

Or manually edit `%APPDATA%\Claude\claude_desktop_config.json`:

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

**Restart Claude Desktop** and look for "revit" in Settings → Developer → MCP Servers.

---

## 💬 Real-World Examples

### Example 1: Build a House

**Prompt to Claude:**
> "Create a 30ft by 25ft rectangular house with 10ft tall walls on Level 1. Add a door and 3 windows."

**What Happens:**
```python
# Claude automatically calls these tools:
revit.create_level(name="Level 1", elevation=0)
revit.create_wall(start_point=(0,0), end_point=(30,0), level="Level 1", height=10)
revit.create_wall(start_point=(30,0), end_point=(30,25), level="Level 1", height=10)
revit.create_wall(start_point=(30,25), end_point=(0,25), level="Level 1", height=10)
revit.create_wall(start_point=(0,25), end_point=(0,0), level="Level 1", height=10)
revit.create_door(wall_id=123, location=15, level="Level 1")
revit.create_window(wall_id=124, location=7.5, level="Level 1")
# ... more windows
```

**Result:** A fully modeled house in Revit, created in seconds.

---

### Example 2: Parametric Twisted Tower

**Prompt to Claude:**
> "Build a 10-story twisted tower. Each floor should rotate 45 degrees from the previous one. Make it octagonal."

**What Happens:**
```python
# Claude generates parametric geometry:
import math

levels = [revit.create_level(name=f"L{i}", elevation=i*14) for i in range(10)]

for i in range(10):
    rotation = i * 45  # Degrees
    radius = 25  # feet

    # Generate octagon points
    points = []
    for j in range(8):
        angle = math.radians(rotation + j * 45)
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        points.append({'x': x, 'y': y})

    # Create floor
    revit.create_floor(boundary_points=points, level=f"L{i}")

    # Create walls connecting to next floor
    # ...
```

**Result:** A 10-story parametric tower with twisted geometry, built automatically.

---

### Example 3: Query and Report

**Prompt to Claude:**
> "How many walls are in the current project? Group them by type and show me the total length of each type."

**What Happens:**
```python
# Claude calls:
elements = revit.get_elements(category="Walls")
# Processes results and generates report
```

**Result:**
```
Wall Summary:
- Basic Wall: 48 walls, 1,245 linear feet
- Curtain Wall: 12 walls, 380 linear feet
- Storefront: 8 walls, 220 linear feet
Total: 68 walls, 1,845 linear feet
```

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────┐
│ AI LAYER                                            │
│  • Claude Desktop                                   │
│  • Microsoft Copilot Studio                         │
│  • Custom MCP Clients                               │
└────────────────────┬────────────────────────────────┘
                     │ MCP Protocol (stdio/HTTP)
          ┌──────────▼──────────────┐
          │ MCP Server (Python)     │
          │  - Tool Registry        │
          │  - Request Validation   │
          │  - Security/Audit       │
          │  - Workspace Sandbox    │
          └──────────┬──────────────┘
                     │ HTTP (localhost:3000)
          ┌──────────▼──────────────┐
          │ Revit Bridge (C#)       │
          │  - HTTP Server          │
          │  - CommandQueue         │
          │  - ExternalEventHandler │
          │  - Reflection Engine    │
          └──────────┬──────────────┘
                     │ Revit API
          ┌──────────▼──────────────┐
          │ Autodesk Revit          │
          │  - Active Document      │
          │  - 3D Model             │
          │  - Views & Sheets       │
          └─────────────────────────┘
```

### Threading Model

The bridge uses **Revit's ExternalEvent** mechanism to ensure thread safety:

1. **HTTP Request** arrives on background thread (BridgeServer)
2. **Request Queued** into thread-safe CommandQueue
3. **ExternalEvent Raised** to Revit main thread
4. **Command Executed** with full Revit API access
5. **Response Returned** via TaskCompletionSource correlation
6. **HTTP Response** sent back to MCP client

**Latency:** Typically <100ms for simple operations, <2s for complex geometry.

---

## 🛠️ Available Tools (105+)

### Document & Session Management
- `revit.create_new_document` - Create blank Revit project
- `revit.open_document` - Open existing RVT/RFA file
- `revit.save_document` - Save active document
- `revit.close_document` - Close document
- `revit.get_document_info` - Get project metadata

### Levels & Grids
- `revit.create_level` - Create new level
- `revit.list_levels` - List all levels
- `revit.create_grid` - Create grid line

### Geometry Creation
- `revit.create_wall` - Create wall between two points
- `revit.create_floor` - Create floor from boundary points
- `revit.create_roof` - Create roof (flat or sloped)
- `revit.create_ceiling` - Create ceiling
- `revit.create_door` - Place door in wall
- `revit.create_window` - Place window in wall
- `revit.create_column` - Create structural column
- `revit.create_beam` - Create structural beam
- `revit.create_room` - Create room boundary

### Views & Visualization
- `revit.create_floor_plan` - Create floor plan view
- `revit.create_ceiling_plan` - Create ceiling plan view
- `revit.create_section_view` - Create section view
- `revit.create_3d_view` - Create 3D view
- `revit.list_views` - List all views
- `revit.activate_view` - Set active view

### Sheets & Documentation
- `revit.create_sheet` - Create new sheet
- `revit.list_sheets` - List all sheets
- `revit.place_view_on_sheet` - Place view on sheet

### Element Operations
- `revit.get_elements` - Query elements by category/filter
- `revit.get_element_properties` - Get parameter values
- `revit.set_element_properties` - Update parameter values
- `revit.delete_elements` - Delete elements by ID

### Family Management
- `revit.load_family` - Load family from RFA file
- `revit.list_families` - List loaded families
- `revit.place_family_instance` - Place family instance

### Export Operations
- `revit.export_pdf` - Export views to PDF
- `revit.export_dwg` - Export views to DWG
- `revit.export_ifc` - Export model to IFC
- `revit.export_nwc` - Export to Navisworks

### Utilities
- `revit.get_wall_types` - List available wall types
- `revit.get_floor_types` - List floor types
- `revit.get_view_filters` - List view filters

**Full Tool Reference:** [docs/tools.md](docs/tools.md)

---

## 📚 Documentation

### Core Documentation
- **[Installation Guide](docs/install.md)** - Detailed installation instructions
- **[Architecture Overview](docs/architecture.md)** - System design and threading model
- **[API Reference](docs/tools.md)** - Complete tool catalog with examples
- **[Security Model](docs/security.md)** - Threat analysis and hardening

### Integration Guides
- **[Claude Desktop Setup](CLAUDE_DESKTOP_SETUP.md)** - Natural language control with Claude
- **[Microsoft Copilot Integration](docs/copilot-integration.md)** - Enterprise conversational AI
- **[Custom MCP Clients](docs/custom-clients.md)** - Build your own integrations

### Development
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute
- **[Development Setup](docs/development.md)** - Build from source
- **[Testing Guide](TESTING_CHECKLIST.md)** - Test procedures
- **[Changelog](CHANGELOG.md)** - Version history

---

## 🧪 Testing

### Run Unit Tests

```powershell
cd packages/mcp-server-revit
pytest tests/ -v --cov
```

### Test with Claude Desktop

1. **Start Revit 2024**
2. **Open Claude Desktop**
3. **Type:**
   ```
   "Create a 20ft by 20ft room on Level 1"
   ```

4. **Verify** the room appears in Revit

### Test Bridge Directly

```powershell
# Test health endpoint
curl http://localhost:3000/health

# Test tool execution
curl -X POST http://localhost:3000/execute `
  -H "Content-Type: application/json" `
  -d '{"tool":"revit.list_levels","payload":{},"request_id":"test1"}'
```

---

## 🔐 Security

### Default: Localhost Only

Out of the box, the bridge binds to `127.0.0.1:3000` (loopback interface only):
- ✅ **Zero network exposure**
- ✅ **No authentication required**
- ✅ **Safe for single-user workstations**

### Enterprise Mode (Optional)

For remote access or Copilot integration, enable enterprise security:

```json
{
  "bridge": {
    "bind_address": "0.0.0.0",
    "https_enabled": true,
    "oauth2": {
      "enabled": true,
      "tenant_id": "your-tenant-id",
      "client_id": "your-client-id"
    },
    "rate_limit": {
      "requests_per_minute": 100
    }
  }
}
```

**Security Features:**
- 🔒 **HTTPS with TLS 1.2+**
- 🔑 **OAuth2 JWT validation (Entra ID)**
- 📝 **Structured audit logging (JSONL)**
- 🚧 **Path allowlisting and validation**
- ⏱️ **Rate limiting per client**
- 🔍 **Request/response inspection**

**See:** [Security Model](docs/security.md) for detailed threat analysis.

---

## 🏗️ Project Structure

```
Autodesk-Revit-MCP-Server/
├── packages/
│   ├── revit-bridge-addin/          # C# Revit Add-in
│   │   ├── src/
│   │   │   └── Bridge/
│   │   │       ├── App.cs           # IExternalApplication entry point
│   │   │       ├── BridgeServer.cs  # HTTP server (localhost:3000)
│   │   │       ├── CommandQueue.cs  # Thread-safe request queue
│   │   │       ├── ExternalEventHandler.cs  # Revit API executor
│   │   │       ├── BridgeCommandFactory.cs  # Tool dispatcher
│   │   │       ├── BridgeCommands.cs  # Ribbon UI commands
│   │   │       └── ReflectionHelper.cs  # Universal API access
│   │   └── RevitBridge.csproj
│   │
│   └── mcp-server-revit/            # Python MCP Server
│       ├── src/revit_mcp_server/
│       │   ├── mcp_server.py        # MCP protocol implementation
│       │   ├── server.py            # Main FastAPI server
│       │   ├── bridge/
│       │   │   ├── client.py        # HTTP bridge client
│       │   │   └── mock.py          # Mock mode for testing
│       │   ├── tools/
│       │   │   ├── handlers.py      # Tool implementations
│       │   │   ├── document.py      # Document operations
│       │   │   └── health.py        # Health checks
│       │   ├── security/
│       │   │   ├── workspace.py     # Path validation
│       │   │   └── audit.py         # JSONL audit logging
│       │   ├── config.py            # Configuration management
│       │   ├── schemas.py           # Pydantic schemas
│       │   └── errors.py            # Exception classes
│       └── tests/                   # Pytest test suite
│
├── scripts/
│   ├── build-addin.ps1              # Build C# add-in
│   ├── install.ps1                  # Deploy add-in to Revit
│   ├── package.ps1                  # Create distribution package
│   └── setup-claude-desktop.ps1     # Configure Claude Desktop
│
├── docs/
│   ├── architecture.md              # System design
│   ├── tools.md                     # Tool reference
│   ├── security.md                  # Security model
│   ├── install.md                   # Installation guide
│   ├── copilot-integration.md       # Copilot setup
│   └── revit-api-capabilities.md    # Revit API coverage
│
├── .github/workflows/
│   └── build.yml                    # CI/CD pipeline
│
├── README.md                        # This file
├── LICENSE                          # MIT License
├── CONTRIBUTING.md                  # Contribution guidelines
└── SECURITY.md                      # Security policy
```

---

## 🤝 Contributing

We welcome contributions from the AEC and developer community!

### How to Contribute

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Add tests** for new functionality
4. **Run tests** (`pytest tests/ -v`)
5. **Commit** with conventional commits (`git commit -m 'feat: add amazing feature'`)
6. **Push** to your branch (`git push origin feature/amazing-feature`)
7. **Open** a Pull Request

### Development Setup

```powershell
# Clone your fork
git clone https://github.com/YOUR_USERNAME/Autodesk-Revit-MCP-Server.git
cd Autodesk-Revit-MCP-Server

# Install dev dependencies
pip install -e "packages/mcp-server-revit[dev]"

# Build add-in
.\scripts\build-addin.ps1 -RevitVersion 2024

# Run tests
pytest packages/mcp-server-revit/tests/ -v --cov

# Format code
ruff check packages/mcp-server-revit/src
ruff format packages/mcp-server-revit/src
```

### Code Standards

- **Python**: Follow PEP 8, use Ruff for linting
- **C#**: Follow Microsoft C# Coding Conventions
- **Documentation**: Update docs for new features
- **Tests**: Maintain >80% code coverage
- **Commits**: Use [Conventional Commits](https://www.conventionalcommits.org/)

**See:** [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📜 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 Sam-AEC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

[Full MIT License text...]
```

---

## 🙏 Acknowledgments

- **Anthropic** - For the [Model Context Protocol](https://modelcontextprotocol.io) specification
- **Autodesk** - For the Revit API and developer community
- **Contributors** - Everyone who has contributed code, bug reports, and feedback

Built with ❤️ for the **Architecture, Engineering, and Construction (AEC) community**.

---

## 📞 Support

### Get Help

- 📖 **[Documentation](docs/)** - Comprehensive guides and API reference
- 💬 **[GitHub Discussions](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/discussions)** - Ask questions and share ideas
- 🐛 **[Issue Tracker](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues)** - Report bugs or request features
- 🔒 **[Security Policy](SECURITY.md)** - Responsible disclosure

### Commercial Support

For enterprise support, custom integrations, or training:
- Email: support@example.com (update with actual contact)
- Website: https://example.com (update with actual website)

---

## 🗺️ Roadmap

### v1.1 (Q1 2025)
- [x] Claude Desktop integration
- [x] 105+ tools covering Revit API
- [x] Parametric design support
- [ ] Enhanced MEP system support
- [ ] Graphical UI for bridge configuration

### v1.2 (Q2 2025)
- [ ] Microsoft Copilot Studio production deployment
- [ ] Multi-user collaboration support
- [ ] Advanced rendering and visualization
- [ ] BIM 360/ACC integration
- [ ] Carbon/energy analysis tools

### v2.0 (Q3 2025)
- [ ] Python API for custom workflows
- [ ] Plugin marketplace
- [ ] Advanced AI agents (code generation, optimization)
- [ ] Cross-platform support (Linux via Wine, macOS via Parallels)

**See:** [CHANGELOG.md](CHANGELOG.md) for version history.

---

## 📊 Status

- ✅ **Production Ready** - Tested with real-world projects
- ✅ **Actively Maintained** - Regular updates and bug fixes
- ✅ **Community Supported** - Growing user and contributor base
- ⚠️ **Revit 2024/2025 Only** - Older versions not supported
- ⚠️ **Windows Only** - Cross-platform support planned

---

<div align="center">

**Star ⭐ this repository if you find it useful!**

[Report Bug](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues) • [Request Feature](https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues) • [Contribute](CONTRIBUTING.md)

---

**Built by builders, for builders.**

[![GitHub](https://img.shields.io/badge/GitHub-Sam--AEC-181717?style=for-the-badge&logo=github)](https://github.com/Sam-AEC)

[⬆ Back to Top](#autodesk-revit-mcp-server)

</div>
