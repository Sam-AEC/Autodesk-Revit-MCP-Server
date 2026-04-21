# Testing Workflow

Automated tests in this repository are concentrated on the Python MCP package under [packages/mcp-server-revit/tests](../packages/mcp-server-revit/tests/).

## Current Test Surface

The existing test files include:

- `test_config.py`
- `test_server.py`
- `test_tools.py`
- `conftest.py`

## What Is Covered

From the current test layout and code, the automated suite primarily covers:

- configuration loading
- environment variable handling
- server-level tool dispatch
- mock-mode execution behavior
- tool registration and handler behavior

This is a useful baseline because it validates the MCP-facing Python layer without requiring a live Revit session.

## What Is Not Covered At The Same Depth

The C# bridge side does not have an equally visible automated test surface in this repo.

That means several important behaviors are still validated mostly through build or manual testing:

- `HttpListener` startup in Revit
- `ExternalEvent` execution on the UI thread
- live Revit API mutation behavior
- ribbon and icon loading
- add-in startup and shutdown inside Revit

## Practical Testing Strategy

In practice the repo supports two different validation loops:

### Fast Loop

Use Python tests in mock mode to validate:

- schemas
- config behavior
- handler routing
- bridge-client abstraction behavior

### Slow Loop

Use manual Revit runs to validate:

- add-in load behavior
- localhost bridge reachability
- real document operations
- export tools against actual Revit models

## Why Mock Mode Matters

Because `mock` is the default mode, CI and developer machines can still validate the MCP server without:

- Windows-only Revit installs
- Autodesk licensing concerns
- UI-thread execution constraints

That is the main reason the Python-side tests are valuable even though they do not exercise the full live stack.

## Working Rule

Treat Python tests as contract and routing validation, not full production proof. Any PR that changes bridge routing, Revit API behavior, or build targets still needs at least one live Revit validation pass before it should be trusted operationally.
