# First check: from install to ready

Status: on the dev branch, not yet released.

This page is for a BIM coordinator setting up AEC Model Bridge for the first
time. You do not need to use a terminal for the installer path. For the full
install options, see [install](install.md).

## The path

1. **Install.** Download `AECModelBridge-Setup-<version>.exe` from the
   [latest release](https://github.com/Sam-AEC/aec-model-bridge/releases/latest)
   and run it with Revit closed (details in [install](install.md#download-the-installer)).
2. **Start Revit** and open a project (not just the start screen). Look for the
   **AEC Bridge** tab.
3. **Open the panel** from the AEC Bridge tab. The **Setup check** card sits at
   the top of the panel and runs by itself when the panel loads.
4. **Read the card.**
   - `Ready` means every check passed. The card shrinks to one line; press
     **Details** to see each check.
   - `N steps to fix` means at least one check failed. Each failing check shows
     **What to do**. Do that step, then press **Refresh**.

Each check is shown with a tick or a `!` and the words "OK" or "Needs
attention", so it does not depend on colour.

## What each check means and how to recover

| Check | Panel label | If it fails |
|---|---|---|
| `hub` | Panel hub | The panel cannot reach the bridge server. Start it from the Connection panel on the AEC Bridge tab, then press **Refresh**. If the port is taken by another program, see "Bridge connection refused" in [install](install.md#bridge-connection-refused). |
| `mode` | Live Revit mode | The hub is in mock mode and returns generated sample data, not your model. Set `MCP_REVIT_MODE` to `bridge` and restart the hub. Mock mode is only for trying the tools without Revit (see [install](install.md#mock-mode)). |
| `revit_bridge` | Revit connection | No running Revit has the add-in loaded. Open Revit with the AEC Bridge tab present and a project open, then press **Refresh**. If Revit is open, check that the installed add-in year matches your Revit year ([install](install.md#requirements)), and check `%APPDATA%\AECModelBridge\Logs\bridge.jsonl`. |
| `workspace` | Workspace folder | The folder where reports are written cannot be written to. Set `MCP_REVIT_WORKSPACE_DIR` to a folder you can write to (absolute path, also listed in `MCP_REVIT_ALLOWED_DIRECTORIES`) and restart the hub. See [install](install.md#workspace-access-denied). |
| `ai_provider` | AI provider for chat | Chat has no AI to talk to. Set `MCP_REVIT_ANTHROPIC_API_KEY`, or install and sign in to the `claude` CLI, then restart Revit. Plans, findings and reports do not need this. |

If the panel cannot reach the hub at all, the card shows a single failing
"Panel hub" check with the error and the same recovery step, and other errors
that say "Could not reach the AEC Model Bridge hub" are replaced by the failing
check's step.

## If the card stays on "Checking setup"

The panel asks Revit's add-in for the check and the add-in asks the hub's
`GET /diagnostics` endpoint on `127.0.0.1` (port `8787` unless
`MCP_PANEL_HTTP_PORT` is set). If it never answers, restart Revit and check the
bridge log named above.

## For IT and scripting

The same data is available from the hub:

```powershell
$panelToken = (Get-Content "$env:LOCALAPPDATA\AECModelBridge\panel-hub.token" -Raw).Trim()
Invoke-RestMethod "http://127.0.0.1:8787/diagnostics" -Headers @{"X-AMB-Token" = $panelToken}
```

It returns `{ "ok": <all checks passed>, "approval_mode": "look_only|ask_first|auto", "approval_mode_note": "<one line>", "checks": [ { "id", "ok", "detail", "next_step" } ] }`.
`next_step` is empty for passing checks. The `approval_mode` check is
informational for `look_only` and `ask_first` and fails for `auto`, because
`auto` skips approvals. The response also includes `dev_mode` and `auto_expires_at`: explicit Dev mode skips approvals until switched off and has no expiry, while panel Auto is timed. `/health` stays a minimal status payload and does not require the token. See [ADR 0018](0018-explicit-development-mode.md).
