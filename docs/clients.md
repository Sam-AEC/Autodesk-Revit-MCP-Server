# Other MCP clients

Status: **UNVERIFIED.** File locations and snippets below come from memory of each client's documentation. None has been tested on a live install. If something does not match, check the client's own docs and open an issue.

Before you start, finish the [install guide](install.md) (the Revit add-in is a separate install) and install [uv](https://docs.astral.sh/uv/) so `uvx` is on your PATH. Each entry starts the server in live mode; set `MCP_REVIT_MODE` to `mock` to try it with sample data and no Revit. Menu names change between versions.

After saving, ask the assistant to list the AEC Model Bridge tools. With Revit open and the **AEC Bridge** tab visible, ask it to read the model name. Model changes stay blocked until you approve a plan in the Revit panel, whatever auto-approve the client has. See [privacy](privacy.md) and [security](security.md).

## Cline (VS Code)

*MCP Servers, Installed, Configure MCP Servers* opens `cline_mcp_settings.json`. Cline can also install by itself from [llms-install.md](../llms-install.md). Leave its auto-approve off for tools that change the model.

```json
{"mcpServers":{"aec-model-bridge":{"command":"uvx","args":["--from","git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit","aec-model-bridge"],"env":{"MCP_REVIT_MODE":"bridge"}}}}
```

## OpenAI Codex (CLI and IDE)

`~/.codex/config.toml` (Windows: `%USERPROFILE%\.codex\config.toml`), or run `codex mcp add`. Codex may ask before running tools; that is separate from the Revit approval gate.

```toml
[mcp_servers.aec-model-bridge]
command = "uvx"
args = ["--from", "git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit", "aec-model-bridge"]
env = { MCP_REVIT_MODE = "bridge" }
```

## Gemini CLI

`~/.gemini/settings.json` (Windows: `%USERPROFILE%\.gemini\settings.json`), or `.gemini/settings.json` in one project. Add it next to existing settings. `/mcp` lists connected servers. There is no `gemini-extension.json` yet, so `gemini extensions install` does not work.

```json
{"mcpServers":{"aec-model-bridge":{"command":"uvx","args":["--from","git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit","aec-model-bridge"],"env":{"MCP_REVIT_MODE":"bridge"}}}}
```

## JetBrains IDEs (AI Assistant)

*Settings, Tools, AI Assistant, Model Context Protocol (MCP), Add*, then choose "As JSON" and paste. The IDE keeps the file itself. Junie has its own MCP settings, not checked here.

```json
{"mcpServers":{"aec-model-bridge":{"command":"uvx","args":["--from","git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit","aec-model-bridge"],"env":{"MCP_REVIT_MODE":"bridge"}}}}
```

## Visual Studio 2022 (17.14 or later) and 2026

`.mcp.json` next to the `.sln`, or `%USERPROFILE%\.mcp.json` for all solutions. It may also read `.vscode/mcp.json`; this repository ships [one](../.vscode/mcp.json). Note the top-level `servers` key. Use Copilot Chat in agent mode and confirm the server the first time.

```json
{"servers":{"aec-model-bridge":{"command":"uvx","args":["--from","git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit","aec-model-bridge"],"env":{"MCP_REVIT_MODE":"bridge"}}}}
```

## Windsurf

`%USERPROFILE%\.codeium\windsurf\mcp_config.json` (Cascade panel, MCP servers, configure). Create it if missing, or add to the existing `mcpServers`. Refresh the MCP list after saving.

```json
{"mcpServers":{"aec-model-bridge":{"command":"uvx","args":["--from","git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit","aec-model-bridge"],"env":{"MCP_REVIT_MODE":"bridge"}}}}
```
