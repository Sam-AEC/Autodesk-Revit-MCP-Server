# Contributing to MCP Revit Bridge

Thank you for considering contributing to MCP Revit Bridge. This document provides guidelines for contributions.

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git
- For bridge development: Windows 10/11, Revit 2020-2024, Visual Studio or MSBuild

### Setup Development Environment

1. Fork and clone the repository:
```bash
git clone https://github.com/Sam-AEC/mcp.git
cd mcp
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install in development mode:
```bash
pip install -e packages/mcp-server-revit[dev]
```

4. Install pre-commit hooks:
```bash
pre-commit install
```

## Development Workflow

### Making Changes

1. Create a feature branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes following the code style guidelines below

3. Run tests:
```bash
pytest packages/mcp-server-revit/tests -v
```

4. Run linter:
```bash
ruff check packages/mcp-server-revit/src
ruff format packages/mcp-server-revit/src
```

5. Commit with descriptive messages:
```bash
git commit -m "Add export_nwc tool for Navisworks export"
```

6. Push to your fork:
```bash
git push origin feature/your-feature-name
```

7. Open a pull request

### Pull Request Guidelines

- Describe what the PR does and why
- Reference any related issues
- Ensure all tests pass
- Update documentation if adding/changing tools
- Keep PRs focused (one feature/fix per PR)

## Code Style

### Python

- Follow PEP 8
- Use type hints for all function signatures
- Use Pydantic models for all schemas
- Maximum line length: 120 characters
- Use ruff for linting and formatting

Example:
```python
def my_tool(payload: dict, workspace: WorkspaceMonitor) -> dict:
    """Execute my custom tool.

    Args:
        payload: Tool input as dictionary
        workspace: Workspace monitor for path validation

    Returns:
        Tool output as dictionary
    """
    input_model = MyToolInput(**payload)
    # Implementation
    return MyToolOutput(result="success").model_dump()
```

### C#

- Follow Microsoft C# coding conventions
- Use explicit types (avoid `var` except for obvious cases)
- Document public methods with XML comments
- Handle exceptions at appropriate boundaries

Example:
```csharp
/// <summary>
/// Exports the active document to NWC format
/// </summary>
/// <param name="outputPath">Full path to output file</param>
/// <returns>Export result with file path</returns>
public ExportResult ExportNWC(string outputPath)
{
    // Implementation
}
```

### Documentation

- Use Markdown for all documentation
- Keep sentences short and direct
- Prefer bullets and numbered lists
- Include code examples for new tools
- Update [CHANGELOG.md](CHANGELOG.md) for all changes

## Adding New Tools

New tools require changes across multiple files. Follow this checklist:

### 1. Define Schemas

Edit [packages/mcp-server-revit/src/revit_mcp_server/schemas.py](packages/mcp-server-revit/src/revit_mcp_server/schemas.py):

```python
class MyToolInput(RequestPayload):
    document_id: str = Field(..., description="Document identifier")
    parameter_name: str = Field(..., description="Parameter to retrieve")

class MyToolOutput(BaseModel):
    parameter_value: str = Field(..., description="Retrieved parameter value")
```

### 2. Implement Mock Handler

Edit [packages/mcp-server-revit/src/revit_mcp_server/tools/handlers.py](packages/mcp-server-revit/src/revit_mcp_server/tools/handlers.py):

```python
def my_tool(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = MyToolInput(**payload)
    # Mock implementation for testing
    return MyToolOutput(parameter_value="mock_value").model_dump()

# Register in TOOL_HANDLERS
TOOL_HANDLERS["revit.my_tool"] = my_tool
```

### 3. Implement Bridge Handler (Optional)

Edit [packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs](packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs):

```csharp
case "revit.my_tool":
    string docId = payload["document_id"].ToString();
    string paramName = payload["parameter_name"].ToString();
    // Real Revit API implementation
    var value = GetParameterValue(docId, paramName);
    return new { parameter_value = value };
```

### 4. Add Tests

Edit [packages/mcp-server-revit/tests/test_tools.py](packages/mcp-server-revit/tests/test_tools.py):

```python
def test_my_tool(workspace_monitor):
    payload = {
        "request_id": "test_001",
        "document_id": "doc_123",
        "parameter_name": "Height"
    }
    result = my_tool(payload, workspace_monitor)
    assert "parameter_value" in result
    assert result["parameter_value"] == "mock_value"
```

### 5. Document the Tool

Add to [docs/tools.md](docs/tools.md) following the existing format with:
- Purpose
- Input schema
- Output schema
- Example request/response

### 6. Update Changelog

Add entry to [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`:

```markdown
### Added
- `revit.my_tool`: Retrieve parameter values from documents
```

## Workspace Constraints

All file operations must respect workspace sandboxing:

```python
# Good: Validate paths through workspace monitor
safe_path = workspace.assert_in_workspace(Path(input_model.file_path))
with open(safe_path, 'w') as f:
    f.write(data)

# Bad: Direct file access without validation
with open(input_model.file_path, 'w') as f:  # Will raise WorkspaceViolation!
    f.write(data)
```

Never bypass the workspace monitor. All paths must be:
- Absolute (not relative)
- Within configured `allowed_directories`
- Resolved (no symlink tricks)

## Testing

### Running Tests

```bash
# All tests
pytest packages/mcp-server-revit/tests

# Specific test file
pytest packages/mcp-server-revit/tests/test_tools.py

# With coverage
pytest --cov=revit_mcp_server packages/mcp-server-revit/tests
```

### Test Requirements

- All new tools must have unit tests
- Tests must pass in mock mode (no Revit dependency)
- Workspace violations must be tested
- Schema validation must be tested

### Mock Mode Testing

Tests run in mock mode by default:

```python
@pytest.fixture
def config():
    return MCPConfig(
        mode=BridgeMode.MOCK,
        workspace_dir=Path("/tmp/test"),
        allowed_directories=[Path("/tmp/test")]
    )
```

## Security Considerations

- Never add tools that bypass workspace sandboxing
- All inputs must be validated with Pydantic schemas
- Log security-relevant operations
- Document any security implications of new tools

See [docs/security.md](docs/security.md) for the security model.

## Documentation Updates

Update documentation when:
- Adding new tools → Update [docs/tools.md](docs/tools.md)
- Changing architecture → Update [docs/architecture.md](docs/architecture.md)
- Changing security model → Update [docs/security.md](docs/security.md)
- Changing installation → Update [docs/install.md](docs/install.md)

## Commit Message Format

Use clear, descriptive commit messages:

```
Add export_nwc tool for Navisworks export

- Implement schema for NWC export configuration
- Add mock handler returning stub file path
- Add bridge handler using NavisworksExportOptions
- Document in tools.md with examples
- Add tests for schema validation
```

Format: `<type>: <subject>`

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `chore`: Maintenance tasks

## Getting Help

- Open an issue for bugs or feature requests
- Tag issues with appropriate labels: `bug`, `enhancement`, `documentation`, `question`
- Join discussions for design questions

## Code of Conduct

Be respectful and professional in all interactions. We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
