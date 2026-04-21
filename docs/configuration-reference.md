# Configuration Reference

This document explains how the Python MCP server resolves runtime configuration from environment variables and `.env` files.

## Source Of Truth

Runtime configuration is defined in [packages/mcp-server-revit/src/revit_mcp_server/config.py](../packages/mcp-server-revit/src/revit_mcp_server/config.py).

The `Config` settings model is built with `pydantic-settings` and uses the `MCP_REVIT_` prefix.

## `.env` Resolution Order

Before the settings model is instantiated, `config.py` attempts to load `.env` from these locations in order:

1. repository root
2. current working directory
3. package root
4. fallback `load_dotenv()` from the current directory

This matters because local development, packaged execution, and script-driven execution may all start from different working directories.

## Core Settings

- `MCP_REVIT_WORKSPACE_DIR`: required root workspace path
- `MCP_REVIT_ALLOWED_DIRECTORIES`: required allowed directory list
- `MCP_REVIT_BRIDGE_URL`: optional bridge endpoint, used in bridge mode
- `MCP_REVIT_MODE`: `mock` or `bridge`
- `MCP_REVIT_AUDIT_LOG`: audit output path
- `MCP_REVIT_LOG_LEVEL`: log verbosity for the Python process

## Allowed Directory Parsing

`allowed_directories` is declared as `List[DirectoryPath]`, but `config.py` accepts a raw string and splits it on semicolons before validation.

Implications:

- Windows-style values such as `C:\work;C:\exports` are supported directly
- every path must resolve to an existing directory because `DirectoryPath` enforces existence
- malformed JSON in env values falls back to raw string handling through the custom `_RawEnvSource`

## Bridge Mode Enum

Execution mode is represented by `BridgeMode`:

- `mock`
- `bridge`

The default is `mock`, which keeps local test and CI runs safe when Revit is not available.

## Workspace Enforcement Hook

The `Config.workspace_allowed()` helper resolves an incoming path and checks whether it is relative to any configured allowed directory.

That means effective path validation depends on both:

- correct `MCP_REVIT_ALLOWED_DIRECTORIES`
- callers resolving paths consistently before writing files

## Operational Rule

If the server behaves differently across shells or launchers, check the working directory first. In this repo, `.env` discovery is intentionally flexible, so configuration drift usually comes from which launcher script set the process working directory.
