# Configuration reference

Status: on the dev branch, not yet released.

This page lists the environment variables, package files and runtime modes of the Revit MCP server.

## Runtime modes

The server has two modes. Set the mode with `MCP_REVIT_MODE`.

- `mock`: uses built-in sample data. Use it for tests, development and trying the tools without Revit. This is the default.
- `bridge`: connects to a running Revit add-in. The server finds the add-in through its local registry entry, or through an explicit bridge URL.

## Environment variables

| Variable | Required | Default | Description |
|---|---:|---|---|
| `MCP_REVIT_MODE` | No | `mock` | Selects `mock` or `bridge`. Set `bridge` for live Revit. |
| `MCP_REVIT_BRIDGE_URL` | No | auto-discovered | Explicit URL of the Revit bridge. Overrides registry discovery. |
| `MCP_REVIT_HOST_VERSION` | No | newest live Revit | Revit year to pick from the local registry, such as `2024` or `2026`. |
| `MCP_REVIT_ALLOWED_DIRECTORIES` | No | the workspace directory | Directories the server may read and write, separated by semicolons. The path guard checks against exactly this list. A value you set always wins. |
| `MCP_REVIT_WORKSPACE_DIR` | No | `~/Documents/AEC Model Bridge` | Root folder for generated files and workspace-backed tools. The server creates the default folder the first time it needs it, so a one-click install works with no configuration. |
| `MCP_REVIT_AUDIT_LOG` | No | `audit.log` | Path of the audit log. A relative path resolves against the working directory of the server process. See [Logging and audit](logging-and-audit.md). |
| `MCP_REVIT_LOG_LEVEL` | No | `INFO` | Log level of the server. |
| `MCP_REVIT_APPROVAL_MODE` | No | `ask_first` | One of `look_only`, `ask_first` (alias `required`) or `auto`; trimmed and case-insensitive. `look_only` refuses every tool that changes the model and lets reads through. `ask_first` needs a `plan_id` for an approved plan before a model change runs. `auto` turns the approval check off. Any other value fails closed to `ask_first` and logs a warning. The mode cannot be changed over MCP. Live-Revit behaviour is UNVERIFIED. See [Security](security.md). Leave it at `ask_first` unless you have a reason. |
| `MCP_REVIT_ENABLE_USER_MODULES` | No | `false` | Set to `true` to load modules from `%LOCALAPPDATA%\AECModelBridge\modules`. See [Module authoring](module-authoring.md). |
| `MCP_REVIT_ALLOW_PYTHON_HOST` | No | `false` | Set to `true` to allow tools that run raw Python on the host, such as `revit_execute_python`. Leave it off unless you need it. |
| `MCP_REVIT_ANTHROPIC_API_KEY` | No | unset | Anthropic API key for the panel's built-in Claude chat (`agent_native.py`, ADR 0012). If you do not set it, the Claude chat falls back to the `claude` command-line tool when that is on your PATH. If neither is available, no AI provider is available. You can also put the key in a `.env` file. The hub reads it only at startup, so restart Revit after you set or change it. The panel's Settings view cannot set it. |
| `MCP_PANEL_HTTP_PORT` | No | `8787` | Port of the panel hub (loopback only). Read by the hub and by the add-in. |
| `MCP_PANEL_TOKEN_FILE` | No | `%LOCALAPPDATA%\AECModelBridge\panel-hub.token` | Path of the per-user panel hub token file. The first hub to start creates it (owner-only); the hub and every Revit add-in read it. Delete it and restart the hub to rotate the token. Never copy its contents into a config, chat or log. See [Security](security.md). |
| `MCP_REVIT_LEGACY_PORT` | No | unset | Read by the Revit add-in, not the Python server. Set to `true` or `1` to bind the add-in to fixed port `3000` with no authentication. See [Security](security.md). |
| `REVIT_SDK` | Build only | unset | Optional path used by the add-in build scripts. |

## Package and registry files

These files define the Python package and the MCP registry entry:

- `packages/mcp-server-revit/pyproject.toml`
- `packages/mcp-server-revit/manifest.json`
- `server.json`

The package name is `aec-model-bridge`. The official repository is https://github.com/Sam-AEC/aec-model-bridge.

## MCP client example

```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": ["-m", "revit_mcp_server.mcp_server"],
      "env": {
        "MCP_REVIT_MODE": "bridge",
        "MCP_REVIT_HOST_VERSION": "2026",
        "MCP_REVIT_WORKSPACE_DIR": "C:\\RevitProjects",
        "MCP_REVIT_ALLOWED_DIRECTORIES": "C:\\RevitProjects"
      }
    }
  }
}
```

## Notes

- Run the server from the repository root, or from an environment where you installed the package in editable mode.
- For live Revit, install the add-in and start the Revit version you want before you test.
- To use several open Revit versions side by side, add one MCP client entry for each version. Give each entry its own `MCP_REVIT_HOST_VERSION`.
