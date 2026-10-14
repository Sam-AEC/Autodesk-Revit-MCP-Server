# MCP Marketplaces and Client Distribution

Status: on the dev branch, not yet released.

This project is prepared for the major MCP discovery paths that can be handled from a public GitHub repository.

Distribution files added for listings are marked UNVERIFIED where they come from documentation read from memory or from a search summary. Treat those as a checklist to confirm, not as tested facts.

Some marketplaces can index the repository automatically once the official MCP Registry entry exists. Others still require a maintainer-owned account, OAuth approval, or a manual web form. Those final publication clicks cannot be completed from the repository alone.

## Primary Listing

### Official MCP Registry

Status: configured.

Files and automation:

- [server.json](../server.json) is the source metadata for the current MCPB release artifact.
- [.github/workflows/publish-mcp.yml](../.github/workflows/publish-mcp.yml) publishes with GitHub OIDC when a release is published or through manual workflow dispatch.
- [.github/workflows/publish-pypi.yml](../.github/workflows/publish-pypi.yml) publishes the optional Python package to PyPI when triggered manually after PyPI trusted publishing is configured.
- [packages/mcp-server-revit/README.md](../packages/mcp-server-revit/README.md) contains the required `mcp-name` ownership marker for PyPI verification if the package is also published to PyPI.

Manual publish from a maintainer machine after installing the official publisher:

```powershell
mcp-publisher login github
mcp-publisher publish
```

Publishing a GitHub release triggers the registry workflow automatically.

The official registry is the feed most downstream MCP galleries and aggregators are expected to scrape.

### GitHub MCP Registry and VS Code MCP Gallery

Status: covered by the official MCP Registry path.

GitHub and VS Code surface MCP servers from registry metadata. After the official registry publish succeeds, this server should be discoverable through the MCP surfaces that consume that registry. No separate VS Code extension is required for a standard stdio MCP server.

The repository also includes [.vscode/mcp.json](../.vscode/mcp.json) so users can install the server into a VS Code workspace directly.

### Claude Code plugin and Claude directory

Status: files in the repository, not submitted anywhere. The plugin schema was written from the Claude Code plugin docs and is UNVERIFIED against the live validator (`claude plugin validate`).

- [.claude-plugin/marketplace.json](../.claude-plugin/marketplace.json) makes this repository a plugin marketplace. Users add it with `/plugin marketplace add Sam-AEC/aec-model-bridge`, then `/plugin install aec-model-bridge@aec-model-bridge`.
- [plugin/](../plugin/) holds the plugin: `.claude-plugin/plugin.json`, `.mcp.json` (the same `uvx` server entry as the README install buttons) and the `revit-review` skill, which teaches an assistant to read, check, draft a plan and then stop for a human to approve.
- Anthropic's directory no longer takes local MCPB (desktop extension) listings as of the 2026-10-09 research (UNVERIFIED: read from a docs page by a research agent, not re-checked here). A local server such as this one goes in as a plugin, submitted by the maintainer in the Claude developer portal (`claude.ai/directory/manage`, "Plugin bundle"). The `.mcpb` file still works when a user installs it by hand.
- A local connector needs a privacy policy. Draft: [privacy.md](privacy.md), referenced from the `privacy_policies` array in [manifest.json](../packages/mcp-server-revit/manifest.json). The field name is from the MCPB manifest spec as remembered and is UNVERIFIED. Nothing is published until the owner signs off on the policy.
- claude.ai on the web and phones only accepts remote HTTPS connectors, so it cannot reach a Revit running on your own computer.

### VS Code Marketplace and Open VSX

Status: publish steps are in [vscode-extension.yml](../.github/workflows/vscode-extension.yml). They run only when a GitHub release is published (not a pre-release), only when the release tag equals the extension version, and each store only when its secret exists: `VSCE_PAT` for the Visual Studio Marketplace, `OVSX_PAT` for Open VSX. Without the secrets the job does nothing. The publisher accounts, namespace claim and tokens belong to the maintainer. Open VSX serves VSCodium and several VS Code forks.

## Client Configurations

Setup guides for further clients (Visual Studio, JetBrains, Codex, Gemini CLI, Windsurf, Cline) are in [clients.md](clients.md), each marked UNVERIFIED until tested on a live install. Cline can also install from [llms-install.md](../llms-install.md).

### VS Code / GitHub Copilot

The workspace config is already committed at `.vscode/mcp.json`.

For user-level install:

```powershell
code --add-mcp "{`"name`":`"revit-2026`",`"type`":`"stdio`",`"command`":`"python`",`"args`":[`"-m`",`"revit_mcp_server.mcp_server`"],`"env`":{`"MCP_REVIT_MODE`":`"bridge`",`"MCP_REVIT_HOST_VERSION`":`"2026`",`"MCP_REVIT_WORKSPACE_DIR`":`"C:\\RevitProjects`",`"MCP_REVIT_ALLOWED_DIRECTORIES`":`"C:\\RevitProjects`"}}"
```

### Claude Desktop, Cursor, Roo Code, Continue, and Similar Clients

Most desktop MCP clients accept this shape:

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

If the Python package was installed from PyPI, the console script can be used instead:

```json
{
  "mcpServers": {
    "revit": {
      "command": "aec-model-bridge",
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

## Third-Party Directories

These directories usually need either an official registry entry, repository URL submission, or maintainer account verification.

| Directory | Current best path |
| --- | --- |
| PulseMCP | Already mirrors this repo. After official registry publish, claim or ask them to replace the temporary mirror with the official registry entry. |
| MCP.Directory | Submit the GitHub repository URL and optional PyPI package URL through their server submission form. |
| Glama | Let Glama index the official registry entry, then claim/verify the maintainer page if needed. |
| Smithery | This Revit server is local stdio and Windows/Revit-dependent, so use MCPB/local distribution or a manual listing rather than hosted HTTP unless a remote bridge is added. The container in `smithery.yaml` runs mock mode only, so any listing should say it needs Revit for live use. |
| Cline MCP Marketplace | Open an issue in the Cline marketplace repository (UNVERIFIED process: repository link, a 400x400 logo, a reason). Cline installs from [llms-install.md](../llms-install.md). There is no 400x400 logo in this repository yet. |
| MCP.so / MCP Market / MCP Store / Conare / Aibase | Submit the GitHub repository URL and use the client config above. These sites generally crawl README, GitHub metadata, and registry data. |

## Release Checklist

1. Build and attach the `.mcpb` artifact to the GitHub release. `scripts/version.py` keeps the plugin and marketplace versions in step with it.
2. Update `server.json` version, artifact URL, and SHA-256 if the artifact changes.
3. Run `mcp-publisher validate`.
4. Publish to the official MCP Registry.
5. Verify discovery through the registry API.
6. Submit or claim listings on third-party directories.
7. For the Claude directory, the maintainer submits the plugin in the Claude developer portal after the privacy policy is approved.
