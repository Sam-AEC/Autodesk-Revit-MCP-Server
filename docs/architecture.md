# Architecture

This repository rebuilds the Revit-focused MCP server from scratch. The Python MCP server exposes 25 Revit tools via stdio, enforces workspace sandboxing, validates inputs against JSON schemas, and logs every tool call. The Revit bridge add-in is a .NET 4.8 ExternalEvent server that executes the same toolset inside Revit through an HTTP listener. A mock bridge covers CI scenarios.

Key components:
- `packages/mcp-server-revit`: Python MCP server with config, bridge clients, schemas, and tool handlers.
- `packages/revit-bridge-addin`: Revit add-in with ExternalEvent queue, tool command handlers, and HTTP bridge server.
- `examples`, `docs`, `scripts`: onboarding material, example configs, and helper scripts described in the plan.
