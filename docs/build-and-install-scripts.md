# Build And Install Scripts

The `scripts/` directory is the operational entry surface for building, packaging, installing, and running the stack.

## Script Roles

### `scripts/build-addin.ps1`

Builds the C# add-in for a selected Revit version.

Key behavior:

- blocks unsafe execution from `C:\Windows`
- prefers MSBuild discovered through `vswhere`
- falls back to `dotnet build`
- passes `RevitVersion` into `RevitBridge.csproj`

### `scripts/package.ps1`

Creates a distribution package under `dist\RevitMCP`.

Key behavior:

- builds add-in binaries for one or more Revit versions
- copies versioned binaries into `dist\bin\{year}`
- attempts PyInstaller packaging for the Python server
- always builds a wheel as fallback
- writes `default.json` and `README.txt` into the distribution payload

### `scripts/install.ps1`

Installs from a prepared distribution package.

Key behavior:

- auto-triggers packaging if `dist\RevitMCP` is missing
- copies bridge binaries into `C:\ProgramData\RevitMCP\bin`
- installs the add-in manifest into the selected Revit add-in directory
- copies default configuration into `C:\ProgramData\RevitMCP\config`

### `scripts/install-addin.ps1`

Performs the minimal manifest copy for a chosen Revit year.

This is the narrowest install path and is useful when the binaries are already built.

### `scripts/setup.ps1`

Acts as the orchestration script.

It runs:

1. build
2. package
3. optional install

### `scripts/start-server.ps1`

Prepares and launches the Python MCP server.

Key behavior:

- creates `.env` from `.env.example` if needed
- checks Python availability
- installs the Python package in editable mode
- optionally probes `http://127.0.0.1:3000/health` in bridge mode
- launches `python -m revit_mcp_server`

### `scripts/run-server.ps1`

This is the thinnest launch path and only executes `python -m revit_mcp_server`.

## Safety Pattern

The more powerful scripts include a path guard that refuses execution from `C:\Windows`. That is an intentional operational safeguard, not decoration.

## Working Rule

Use `setup.ps1` when you want the full build-package-install path. Use `start-server.ps1` when the add-in is already in place and you only need to validate or run the Python side.
