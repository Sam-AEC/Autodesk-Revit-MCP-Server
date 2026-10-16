# AEC Model Bridge for VS Code

Let Copilot agent mode (and any other MCP client in VS Code) work with your Revit model. This extension registers the [AEC Model Bridge](https://github.com/Sam-AEC/aec-model-bridge) MCP server for you, so there is no JSON to write and no path to look up.

## What it does

- Adds the AEC Model Bridge server to VS Code's MCP servers. Open Copilot Chat in agent mode and the Revit tools are in the tools list.
- Starts the server with the Python that the AEC Model Bridge installer already put on your machine. If that is missing, it falls back to `uvx` and fetches the server from GitHub.
- Shows **Connected (Revit 2026)** or **Not connected** in the status bar, so you know whether Revit is reachable before you ask the AI to do something.
- Has a mock mode that works without Revit, so you can try the tools or build workflows on a laptop with no licence.

## Requirements

- VS Code 1.101 or newer (the version that added the MCP extension API) with GitHub Copilot or another MCP-capable chat.
- Windows. Revit and its add-in only run there.
- Install the extension locally when using SSH, WSL or a dev container. It runs beside your Windows Revit session. Remote workspace folders use your local Documents folder unless you configure a local `workspaceDir`.
- For live Revit: Revit 2024 to 2027 with the AEC Model Bridge add-in installed. Follow the [install guide](https://github.com/Sam-AEC/aec-model-bridge/blob/main/docs/install.md).
- Fallback only: [`uv`](https://docs.astral.sh/uv/) on your PATH, if the bundled Python is not installed.
- Mock mode needs no Revit.

## Getting started

1. Install the AEC Model Bridge add-in (the installer also provides the bundled Python).
2. Install this extension.
3. Open Copilot Chat, switch to agent mode and pick the AEC Model Bridge tools. VS Code asks you to trust the server the first time it starts.
4. Run **AEC Model Bridge: Check connection** from the Command Palette to confirm Revit is reachable.

No Revit yet? Run **AEC Model Bridge: Use mock mode** and carry on.

## Build and install locally

The extension is under local review and is not published to the Marketplace.
From the repository root, use Node.js 22 or newer to build the package:

```powershell
cd extensions/vscode
npm ci
npm run compile
npm test
npm run package
code --install-extension aec-model-bridge-<version>.vsix
```

Use the filename printed by the package command if the repository version has
changed. Compilation and automated tests do not establish live Revit behavior.
Before publishing, check registration in a real VS Code instance, mock startup,
the approval warning and cancellation, configuration changes and restarts,
and connection status against a running Revit add-in. Use a disposable model
for the first live change.

## Commands

| Command | What it does |
| --- | --- |
| AEC Model Bridge: Check connection | Looks for a running Revit and tells you its version, or what to fix. |
| AEC Model Bridge: Open install guide | Opens the install guide on GitHub. |
| AEC Model Bridge: Use mock mode | Switches to simulated data that needs no Revit. |

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `aecModelBridge.mode` | `bridge` | `bridge` talks to a running Revit. `mock` uses simulated data. |
| `aecModelBridge.revitYear` | `auto` | `auto`, `2024`, `2025`, `2026` or `2027`. Pick a year if more than one Revit is open. |
| `aecModelBridge.workspaceDir` | empty | Folder the server may read and write. Empty uses the first folder open in VS Code, or your Documents folder. |
| `aecModelBridge.approvalMode` | `required` | `required` or `auto`. See the safety note below. |
| `aecModelBridge.statusRefreshSeconds` | `30` | How often the status bar re-checks Revit. |

After you change a setting, restart the server from **MCP: List Servers** if it was already running.

## Safety: the approval gate

By default, every action that changes your model has to be approved by you before it runs. The AI proposes a plan, you review it, and only then does it execute. Keep `approvalMode` on `required`.

Setting it to `auto` turns the gate off. The agent can then change or delete things in your model without asking first. The extension shows a warning each time it starts the server in that mode. Use `auto` only on a scratch copy of a model that you can afford to lose.

The server runs on your machine and only talks to Revit through the local add-in. See the [security notes](https://github.com/Sam-AEC/aec-model-bridge/blob/main/docs/security.md) for the full picture. This extension does not run in untrusted workspaces.

## How it works

The extension uses the VS Code MCP extension API: it declares a provider under `contributes.mcpServerDefinitionProviders`, registers it with `vscode.lm.registerMcpServerDefinitionProvider`, and returns a `McpStdioServerDefinition` that launches `python -m revit_mcp_server.mcp_server`. See the [MCP developer guide](https://code.visualstudio.com/api/extension-guides/ai/mcp).

## Links

- [Project and docs](https://github.com/Sam-AEC/aec-model-bridge)
- [Report an issue](https://github.com/Sam-AEC/aec-model-bridge/issues)

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) and the repository's [LICENSING.md](https://github.com/Sam-AEC/aec-model-bridge/blob/main/LICENSING.md).
