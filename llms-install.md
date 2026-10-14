# AEC Model Bridge: install notes for AI agents (Cline)

UNVERIFIED: written for Cline's MCP marketplace flow and not yet tested with Cline.

AEC Model Bridge is an MCP server for Autodesk Revit. It needs Windows. For live work it also needs a licensed Revit 2024 to 2027 and the AEC Model Bridge add-in. Without Revit it runs in mock mode on sample data.

Do these steps in order. Stop and tell the person if a step fails. Do not guess.

1. Check that `uv` is installed: run `uv --version`. If it is missing, ask the person to install it from https://docs.astral.sh/uv/ and wait.
2. Ask the person which mode they want.
   - Mock mode (sample data, no Revit): set `MCP_REVIT_MODE` to `mock`.
   - Live mode (their open Revit): set `MCP_REVIT_MODE` to `bridge`. Tell them the Revit add-in must be installed from https://github.com/Sam-AEC/aec-model-bridge/blob/main/docs/install.md and that you cannot install it for them.
3. Add this to the MCP settings file (`cline_mcp_settings.json`), keeping any servers already there:

```json
{
  "mcpServers": {
    "aec-model-bridge": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Sam-AEC/aec-model-bridge#subdirectory=packages/mcp-server-revit",
        "aec-model-bridge"
      ],
      "env": { "MCP_REVIT_MODE": "bridge" }
    }
  }
}
```

4. Do not set `MCP_REVIT_APPROVAL_MODE`. The default, `ask_first` (older name `required`), blocks every model change until a person approves a plan. `look_only` blocks them entirely. Never turn it off. Explicit panel Dev mode and timed Auto also skip per-change approvals; ask the person to switch them off for this workflow.
5. Ask the person to restart the server in Cline, then list the tools to check it started.

Using the tools safely: read first, draft a plan for any change, then stop and ask the person to approve the plan themselves in the AEC Bridge panel in Revit. Never approve a plan yourself. Do not say a change was made until the result confirms it. More: https://github.com/Sam-AEC/aec-model-bridge/blob/main/plugin/skills/revit-review/SKILL.md

Privacy: https://github.com/Sam-AEC/aec-model-bridge/blob/main/docs/privacy.md
