<div align="center">

<img src="assets/logo.svg" alt="AEC Model Bridge" height="120">

# AEC Model Bridge

AEC Model Bridge is the open, secure runtime that puts Revit, Rhino, Navisworks, and Power BI behind one MCP call center — so an AI agent orchestrates them directly, instead of you manually dumping data between disconnected apps.



[![MCP Registry](https://img.shields.io/badge/MCP_Registry-active-0F766E?style=flat-square)](https://registry.modelcontextprotocol.io/?q=io.github.Sam-AEC%2Faec-model-bridge)
[![License](https://img.shields.io/badge/license-GPLv3%2B%20%2F%20Commercial-2563EB?style=flat-square)](LICENSING.md)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Revit](https://img.shields.io/badge/Revit-2024--2027-0696D7?style=flat-square)](https://www.autodesk.com/products/revit/)

<br>
<strong>Available now</strong><br>

![Revit available](https://img.shields.io/badge/Revit-available-16A34A?style=flat-square)
![Rhino and Grasshopper available](https://img.shields.io/badge/Rhino_%2F_Grasshopper-available-16A34A?style=flat-square)
![IfcOpenShell available](https://img.shields.io/badge/IfcOpenShell-available-16A34A?style=flat-square)
![Speckle available](https://img.shields.io/badge/Speckle-available-16A34A?style=flat-square)

<strong>In progress</strong><br>

![Navisworks Manage in progress](https://img.shields.io/badge/Navisworks_Manage-in_progress-F59E0B?style=flat-square)
![Power BI in progress](https://img.shields.io/badge/Power_BI-in_progress-F59E0B?style=flat-square)

<strong>Coming soon</strong><br>

![Microsoft Excel coming soon](https://img.shields.io/badge/Microsoft_Excel-coming_soon-2563EB?style=flat-square)
![Parquet and DuckDB coming soon](https://img.shields.io/badge/Parquet_%2F_DuckDB-coming_soon-2563EB?style=flat-square)

[Install](#installation) | [Tools](docs/tools-generated.md) | [Documentation](#documentation) | [Latest release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)

</div>

A single MCP client — Claude Desktop, VS Code, GitHub Copilot, or a custom
agent — talks to one Python hub, and the hub routes each call to whichever
app the task actually needs: draw geometry in Rhino, query parameters in
Revit, resolve clashes in Navisworks, publish a dashboard to Power BI. The
agent plans the workflow once; the bridge is what lets it reach every app
without you being the one copying data between them.

The Python hub handles MCP communication and routes each request to the relevant
desktop, headless, cloud, or compute provider:
- **Revit**: Native C# add-in (Revit 2024-2027) executing on the main thread via `ExternalEvent`.
- **Navisworks Manage**: Native C# add-in (Navisworks 2024-2027) exposing the API over a local bridge (in progress).
- **Rhino/Grasshopper**: Connects to the Rhino Bridge Add-in over HTTP localhost:3004.
- **Speckle**: Native Python provider integrating Specklepy V3 for seamless model pushing to Power BI.
- **IfcOpenShell**: Headless IFC semantic extraction and parsing.

## Platform Status

The status below reflects the AEC Model Bridge system blueprint as of June 2026.
In-progress integrations are implemented as routing infrastructure but require further registration or workflow integration.

### Available Now

Revit, Rhino/Grasshopper, IfcOpenShell, and Speckle are available integrations. The Revit C# add-in (Revit 2024-2027) executes commands on the main thread. Rhino connects to the Rhino Bridge Add-in over HTTP on port 3004. IfcOpenShell provides headless IFC parsing, and Speckle integrates model pushing via Specklepy V3.

### In Progress

Navisworks Manage is currently in progress; while the C# add-in routing infrastructure is in place, the provider is not yet registered in the shipped hub. Power BI is also in progress, with the provider and tool in place but not yet integrated into the active hub runtime.

### Coming Soon

This wave adds Excel workbook round trips and a Parquet/DuckDB data plane for cross-platform reporting.

## Highlights

- 100+ MCP tools for model authoring, documentation, parameters, views, sheets, exports, and QA.
- Native Revit & Navisworks add-ins with no Dynamo or pyRevit dependencies.
- Multi-platform synchronization: Cross-query Navisworks clash results, Revit parameters, and Rhino models dynamically.
- Speckle and PowerBI automated data handoffs.
- Async job orchestration and centralized PII redaction.
- Reflection and in-process Python for advanced API workflows.
- Localhost-only bridge by default for absolute security.
- Mock mode for development and automated testing without Revit.

## How It Works

```text
MCP Client (Claude Desktop, VS Code)
    |
    | MCP over stdio
    v
    Python MCP Server (Central Router)
        ├── [Revit Provider] -----> HTTP localhost:3000 -----> Revit Bridge Add-in
        ├── [Navisworks Provider] > HTTP localhost:3002 -----> Navisworks Bridge Add-in
        ├── [Speckle Provider] ---> HTTPS (OAuth) -----------> Speckle Manager / Power BI
        ├── [Rhino Provider] -----> HTTP localhost:3004 -----> Rhino Bridge Add-in
        └── [IFC Provider] -------> Local Filesystem --------> IfcOpenShell
```

## Installation

### Requirements

| Revit version | Add-in target | Required build tools |
|---|---|---|
| 2024 | .NET Framework 4.8 | .NET 8 SDK and .NET Framework 4.8 developer pack |
| 2025 | .NET 8 for Windows | .NET 8 SDK |
| 2026 | .NET 8 for Windows | .NET 8 SDK |
| 2027 | .NET 10 for Windows | .NET 10 SDK |

You also need Windows 10 or 11, Python 3.11 or later, and a licensed Revit
installation for the version you want to use.

### 1. Install the MCP server

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit
```

### 2. Install the Revit add-in

Set the version to match your Revit installation:

```powershell
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"

.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

The installer places version-specific binaries in:

```text
C:\ProgramData\AECModelBridge\bin\<year>
```

The add-in manifest is installed per user in:

```text
%APPDATA%\Autodesk\Revit\Addins\<year>
```

Use `-AllUsers` with `install.ps1` to install the manifest under
`C:\ProgramData\Autodesk\Revit\Addins\<year>` instead.

To prepare binaries for every supported version in one pass:

```powershell
.\scripts\package.ps1 -RevitVersion All
```

Prebuilt packages are attached to GitHub releases when available. The source
installation above is the canonical path for all supported Revit versions.

### 3. Configure your MCP client

Use the Python executable from the virtual environment and choose a workspace
that the server may access:

```json
{
  "mcpServers": {
    "aec-model-bridge": {
      "command": "C:\\path\\to\\aec-model-bridge\\.venv\\Scripts\\python.exe",
      "args": ["-m", "revit_mcp_server.mcp_server"],
      "env": {
        "MCP_REVIT_MODE": "bridge",
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
        "MCP_REVIT_WORKSPACE_DIR": "C:\\RevitProjects",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\RevitProjects"
      }
    }
  }
}
```

VS Code users can start from [`.vscode/mcp.json`](.vscode/mcp.json).

Hermes Desktop users can start from [Hermes/mcp.json] (https://github.com/jyh100/aec-model-bridge/blob/main/Hermes.json)

Clients that support MCP Bundles can install the `.mcpb` file from the
[latest release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest).
The Revit add-in is still required because the MCP server communicates with the
running desktop application.

### 4. Verify the connection

Restart Revit after installing the add-in, open a model, and run:

```powershell
Invoke-RestMethod http://127.0.0.1:3000/health
```

The response should report `healthy` and the active Revit version.

## Revit API Access

The typed MCP tools cover the common workflow surface and are the recommended
default for agents.

For work outside the tool catalog, `invoke_method`, `reflect_get`, and
`reflect_set` can work with public .NET API members. `execute_python` runs
IronPython inside Revit with `doc`, `uidoc`, `uiapp`, and `app` available.

These advanced tools run with the same permissions as the Revit process. Keep
the bridge on localhost and only use trusted MCP clients and prompts.

## Development

```powershell
# Python tests
python -m pytest packages/mcp-server-revit/tests

# Build one Revit version
$RevitVersion = Read-Host "Revit year (2024, 2025, 2026, or 2027)"
.\scripts\build-addin.ps1 -RevitVersion $RevitVersion -Configuration Release

# Build all supported versions
.\scripts\package.ps1 -RevitVersion All
```

CI builds the Python server and add-in targets for Revit 2024 through 2027.

## Documentation

- [Installation guide](docs/install.md)
- [Tool reference](docs/tools-generated.md)
- [Architecture](docs/0001-multi-provider-architecture.md)
- [Configuration reference](docs/configuration-reference.md)
- [Security](docs/security.md)
- [MCP clients and registry](docs/marketplaces.md)
- [Contributing](CONTRIBUTING.md)

## Project

Maintained by [A. Sam Mohammad](https://github.com/Sam-AEC).
[LinkedIn](https://www.linkedin.com/in/a-sam-mohammad-92790416b) |
[Issues](https://github.com/Sam-AEC/aec-model-bridge/issues)

Version 1.1.0 and later is available under your choice of
[GPL-3.0-or-later with the Revit Linking Exception, or a separate commercial
license](LICENSING.md). The GPL option permits community use while allowing the
add-in to operate through Autodesk Revit APIs. Commercial terms are available
for proprietary distribution and negotiated requirements. Version 1.0.2 and
earlier remains available under the MIT License.

AEC Model Bridge is an independent project and is not sponsored, endorsed, or
provided by Autodesk. Autodesk and Revit are trademarks of the Autodesk group
of companies. See [TRADEMARKS.md](TRADEMARKS.md).
