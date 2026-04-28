# MCP Marketplaces and Client Distribution

This project is prepared for the major MCP discovery paths that can be handled from a public GitHub repository.

Some marketplaces can index the repository automatically once the official MCP Registry entry exists. Others still require a maintainer-owned account, OAuth approval, or a manual web form. Those final publication clicks cannot be completed from the repository alone.

## Primary Listing

### Official MCP Registry

Status: configured.

Files and automation:

- [server.json](../server.json) is valid for the official registry and points to the v0.1.1 MCPB release artifact.
- [.github/workflows/publish-mcp.yml](../.github/workflows/publish-mcp.yml) publishes with GitHub OIDC on version tags or manual workflow dispatch.
- [.github/workflows/publish-pypi.yml](../.github/workflows/publish-pypi.yml) publishes the optional Python package to PyPI when triggered manually after PyPI trusted publishing is configured.
- [packages/mcp-server-revit/README.md](../packages/mcp-server-revit/README.md) contains the required `mcp-name` ownership marker for PyPI verification if the package is also published to PyPI.

Manual publish from a maintainer machine after installing the official publisher:

```powershell
mcp-publisher login github
mcp-publisher publish
```

Automated publish from GitHub:

```powershell
git tag v0.1.1
git push origin v0.1.1
```

The official registry is the feed most downstream MCP galleries and aggregators are expected to scrape.

### GitHub MCP Registry and VS Code MCP Gallery

Status: covered by the official MCP Registry path.

GitHub and VS Code surface MCP servers from registry metadata. After the official registry publish succeeds, this server should be discoverable through the MCP surfaces that consume that registry. No separate VS Code extension is required for a standard stdio MCP server.

The repository also includes [.vscode/mcp.json](../.vscode/mcp.json) so users can install the server into a VS Code workspace directly.

## Client Configurations

### VS Code / GitHub Copilot

The workspace config is already committed at `.vscode/mcp.json`.

For user-level install:

```powershell
code --add-mcp "{`"name`":`"revit`",`"type`":`"stdio`",`"command`":`"python`",`"args`":[`"-m`",`"revit_mcp_server.mcp_server`"],`"env`":{`"MCP_REVIT_MODE`":`"bridge`",`"MCP_REVIT_BRIDGE_URL`":`"http://127.0.0.1:3000`",`"MCP_REVIT_WORKSPACE_DIR`":`"C:\\RevitProjects`",`"MCP_REVIT_ALLOWED_DIRECTORIES`":`"C:\\RevitProjects`"}}"
```

### Claude Desktop, Cursor, Windsurf, Cline, Roo Code, Continue, and Similar Clients

Most desktop MCP clients accept this shape:

```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": ["-m", "revit_mcp_server.mcp_server"],
      "env": {
        "MCP_REVIT_MODE": "bridge",
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
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
      "command": "revit-mcp-server",
      "env": {
        "MCP_REVIT_MODE": "bridge",
        "MCP_REVIT_BRIDGE_URL": "http://127.0.0.1:3000",
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
| Smithery | This Revit server is local stdio and Windows/Revit-dependent, so use MCPB/local distribution or a manual listing rather than hosted HTTP unless a remote bridge is added. |
| MCP.so / MCP Market / MCP Store / Conare / Aibase | Submit the GitHub repository URL and use the client config above. These sites generally crawl README, GitHub metadata, and registry data. |

## Release Checklist

1. Build and attach the `.mcpb` artifact to the GitHub release.
2. Update `server.json` version, artifact URL, and SHA-256 if the artifact changes.
3. Run `mcp-publisher validate`.
4. Publish to the official MCP Registry.
5. Verify discovery through the registry API.
6. Submit or claim listings on third-party directories.
