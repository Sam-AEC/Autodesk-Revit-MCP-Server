# Contributing

Thanks for improving Autodesk Revit MCP Server.

## Focus Areas

Contributions are most useful when they improve one of the following:
- Revit command coverage
- MCP tool reliability and error handling
- installation and configuration documentation
- developer ergonomics for local debugging and testing

## Guidelines

- Keep changes scoped to a single feature, fix, or documentation update.
- Document any Revit version assumptions in the PR description.
- Sanitize local paths, machine names, and credentials from config examples.
- If a change affects UI or commands, include reproduction steps and expected behavior.
- Update examples or docs when behavior changes.

## Pull Request Checklist

Before opening a PR, confirm that:
- the change has clear reproduction and validation steps
- config examples still work with placeholder values
- README or docs are updated when setup or behavior changes
- any limitations or known gaps are called out explicitly
