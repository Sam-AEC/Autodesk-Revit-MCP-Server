# Contributing

1. Keep the workspace sandbox constraints in mind: `WORKSPACE_DIR` must cover any files you read/write.
2. Work in the `master` branch (this repo uses a linear history). Commit often, describing the Revit tools or docs you added.
3. Run `python -m pytest packages/mcp-server-revit/tests` before opening a PR.
4. Update documentation (`docs/*.md`) when you add or modify tools, scripts, or workflows.
