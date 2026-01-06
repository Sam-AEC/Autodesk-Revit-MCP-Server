# Release Checklist for v0.1.0

## Final Repository Structure

```
mcp/
├── .github/
│   └── workflows/
│       └── ci.yml                    # GitHub Actions CI (lint + test in mock mode)
├── .pre-commit-config.yaml           # Pre-commit hooks (ruff, trailing whitespace, YAML)
├── assets/
│   ├── logo.svg                      # Project logo
│   └── demo.gif                      # Demo animation (placeholder - needs real GIF)
├── docs/
│   ├── install.md                    # Comprehensive installation guide
│   ├── tools.md                      # Complete tool catalog with schemas/examples
│   ├── architecture.md               # System architecture and design decisions
│   └── security.md                   # Security model and threat boundaries
├── examples/
│   └── revit-mcp-config.json         # Example configuration file
├── packages/
│   ├── mcp-server-revit/
│   │   ├── pyproject.toml            # Python package configuration
│   │   ├── src/
│   │   │   └── revit_mcp_server/
│   │   │       ├── __init__.py
│   │   │       ├── __main__.py       # Entry point
│   │   │       ├── server.py         # MCP protocol handler
│   │   │       ├── config.py         # Environment-based configuration
│   │   │       ├── schemas.py        # Pydantic models for all tools
│   │   │       ├── errors.py         # Custom exceptions
│   │   │       ├── bridge/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── client.py     # HTTP bridge client
│   │   │       │   └── mock.py       # Mock bridge for testing
│   │   │       ├── security/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── workspace.py  # Path sandboxing
│   │   │       │   └── audit.py      # Audit logging
│   │   │       └── tools/
│   │   │           ├── __init__.py
│   │   │           ├── handlers.py   # 25 tool implementations
│   │   │           ├── document.py
│   │   │           └── health.py
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_config.py
│   │       ├── test_server.py
│   │       └── test_tools.py
│   ├── revit-bridge-addin/
│   │   ├── RevitBridge.sln           # Visual Studio solution
│   │   ├── RevitBridge.csproj        # .NET 4.8 project file
│   │   ├── RevitBridge.addin         # Revit add-in manifest
│   │   └── src/
│   │       └── Bridge/
│   │           ├── App.cs            # IExternalApplication entry point
│   │           ├── BridgeServer.cs   # HTTP listener (port 3000)
│   │           ├── BridgeCommandFactory.cs  # Tool router
│   │           └── ExternalEventHandler.cs  # Revit API queue
│   └── client-demo/
│       └── demo.py                   # Example client workflow
├── scripts/
│   ├── dev.ps1                       # Development environment setup
│   ├── run-server.ps1                # Start MCP server
│   ├── run-demo.ps1                  # Run demo client
│   ├── build-addin.ps1               # Build bridge add-in
│   └── install-addin.ps1             # Install add-in to Revit
├── CHANGELOG.md                      # Version history
├── CONTRIBUTING.md                   # Contribution guidelines
├── LICENSE                           # MIT License
├── README.md                         # Main documentation
└── SECURITY.md                       # Security policy and vulnerability reporting
```

## Mock Mode Demo Commands

```bash
# 1. Clone repository
git clone https://github.com/Sam-AEC/mcp.git
cd mcp

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Install MCP server
pip install -e packages/mcp-server-revit[dev]

# 4. Configure environment
export MCP_REVIT_MODE=mock
export WORKSPACE_DIR="$(pwd)/workspace"
export MCP_REVIT_ALLOWED_DIRECTORIES="$(pwd)/workspace"
mkdir -p workspace

# 5. Run tests
pytest packages/mcp-server-revit/tests -v

# 6. Start MCP server (in one terminal)
python -m revit_mcp_server

# 7. Run demo client (in another terminal)
python packages/client-demo/demo.py

# Expected output:
# - Health check: {"status": "healthy", "mode": "mock"}
# - Document opened: mock response with file path
# - Quantities exported: workspace/quantities.csv (mock data)
# - Audit log: workspace/audit.jsonl with request tracking
```

## Bridge Mode Demo Commands (Windows)

```powershell
# 1. Clone repository (same as mock mode)
git clone https://github.com/Sam-AEC/mcp.git
cd mcp

# 2. Install Python package (same as mock mode)
python -m venv venv
venv\Scripts\activate
pip install -e packages/mcp-server-revit[dev]

# 3. Set Revit SDK path
$env:REVIT_SDK = "C:\Program Files\Autodesk\Revit 2024\SDK"

# 4. Build bridge add-in
.\scripts\build-addin.ps1

# 5. Install add-in to Revit 2024
.\scripts\install-addin.ps1 -RevitYear 2024

# 6. Start Revit (bridge loads automatically)

# 7. Configure bridge mode
$env:MCP_REVIT_MODE = "bridge"
$env:MCP_REVIT_BRIDGE_URL = "http://localhost:3000"
$env:WORKSPACE_DIR = "C:\revit-workspace"
$env:MCP_REVIT_ALLOWED_DIRECTORIES = "C:\revit-workspace"
mkdir C:\revit-workspace -ErrorAction SilentlyContinue

# 8. Start MCP server (in one terminal)
python -m revit_mcp_server

# 9. Run demo client (in another terminal)
python packages/client-demo/demo.py

# Expected output:
# - Health check: {"status": "healthy", "mode": "bridge", "revit_version": "2024"}
# - Real Revit operations execute
# - Files created in C:\revit-workspace\
# - Audit log tracks bridge communications
```

## Pre-Release Checklist

### Code Quality
- [x] All tests pass (`pytest packages/mcp-server-revit/tests`)
- [x] Linting passes (`ruff check packages/mcp-server-revit/src`)
- [x] Formatting is consistent (`ruff format packages/mcp-server-revit/src`)
- [x] Type checking passes (`mypy packages/mcp-server-revit/src`)
- [ ] CI pipeline is green (check GitHub Actions)

### Documentation
- [x] README.md is comprehensive with badges and examples
- [x] CHANGELOG.md includes v0.1.0 entry
- [x] docs/install.md covers both mock and bridge modes
- [x] docs/tools.md documents all 25 tools with schemas
- [x] docs/architecture.md explains system design
- [x] docs/security.md covers threat model
- [x] CONTRIBUTING.md provides clear guidelines
- [x] SECURITY.md includes vulnerability reporting

### Visuals
- [x] assets/logo.svg created
- [ ] assets/demo.gif created (currently placeholder - needs real GIF)

### Security
- [x] No personal names or sensitive data in code
- [x] LICENSE updated to generic attribution
- [x] Workspace sandboxing enforced
- [x] Audit logging implemented
- [x] Mock mode safe for CI

### Build & Deploy
- [ ] Test mock mode on fresh clone
- [ ] Test bridge mode on Windows with Revit 2024
- [ ] Verify add-in builds without errors
- [ ] Verify add-in installs to correct location
- [ ] Test all PowerShell scripts

### Repository Hygiene
- [x] Unnecessary files removed (history.txt, CODE_OF_CONDUCT.md, redundant READMEs)
- [x] .gitignore comprehensive
- [x] Pre-commit hooks configured
- [x] GitHub Actions CI configured

## Post-Release Tasks

1. **Create GitHub Release**:
   - Tag: `v0.1.0`
   - Title: "MCP Revit Bridge v0.1.0"
   - Description: Copy from CHANGELOG.md
   - Attach demo.gif if created

2. **Update Repository Settings**:
   - Add description: "Connect MCP clients to Autodesk Revit through a Python server and .NET bridge add-in"
   - Add topics: `revit`, `mcp`, `autodesk`, `revit-api`, `automation`, `dotnet`, `python`
   - Enable issues
   - Enable discussions (optional)

3. **Create Demo GIF**:
   - Record 6-10 second screen capture
   - Show: mock mode startup → demo client → output files
   - Optimize to <2MB
   - Replace assets/demo.gif placeholder

4. **Announce**:
   - Post in relevant communities (if applicable)
   - Update mcp-use framework with example (if they accept showcase projects)

## Known Limitations for v0.1.0

- Bridge add-in has stub implementations (returns mock data, no real Revit API calls)
- ExternalEvent pattern not fully implemented
- No async HTTP client (synchronous only)
- Single request at a time (no queuing)
- Limited error handling in bridge
- No request batching

## Roadmap for v0.2.0

- Implement real Revit API operations in bridge
- Add ExternalEvent queue processing
- Async HTTP client in MCP server
- Additional QA tools
- Enhanced sheet automation
- Batch document processing
- Better error messages

## Testing Recommendations

Before releasing:

1. Clone repo fresh to `/tmp/mcp-test`
2. Follow mock mode commands exactly
3. Verify all output artifacts
4. On Windows machine:
   - Install Revit 2024
   - Follow bridge mode commands
   - Verify HTTP listener starts
   - Test at least 3 different tools

## Support Plan

- Monitor GitHub issues
- Respond to bug reports within 48 hours
- Accept PRs for new tools
- Update documentation based on user feedback
