# Extending The Stack

Adding a new capability in this repository usually touches more than one layer. The clean path is cross-cutting by design.

## Layers Involved

A typical end-to-end tool addition spans:

1. Python schema and config-aware input validation
2. Python handler registration
3. bridge transport contract
4. C# routing in `BridgeCommandFactory`
5. live Revit API execution logic
6. tests
7. documentation

## Python Layer

The Python side owns the MCP-facing contract.

Typical files involved:

- [schemas.py](../packages/mcp-server-revit/src/revit_mcp_server/schemas.py)
- [tools/handlers.py](../packages/mcp-server-revit/src/revit_mcp_server/tools/handlers.py)
- [mcp_server.py](../packages/mcp-server-revit/src/revit_mcp_server/mcp_server.py)

This is where payload shape, handler registration, and mode-specific behavior start.

## Bridge Layer

If the tool requires live Revit execution, the bridge must know how to route it.

Typical files involved:

- [BridgeCommandFactory.cs](../packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs)
- [CommandQueue.cs](../packages/revit-bridge-addin/src/Bridge/CommandQueue.cs)
- [ExternalEventHandler.cs](../packages/revit-bridge-addin/src/Bridge/ExternalEventHandler.cs)

The queue and `ExternalEvent` machinery usually do not need a new abstraction per tool, but the route and execution method do.

## Documentation Surface

A real tool addition should update the docs surface too:

- `README.md` if the capability changes the public positioning
- `docs/tools.md` for catalog coverage
- focused operational docs if the behavior introduces new runtime expectations

If the capability changes install, security, or mode assumptions, the surrounding docs should move with it.

## Validation Loop

For a safe addition:

1. add schema and handler coverage
2. add or update Python tests
3. compile the add-in
4. validate the bridge route
5. run a live Revit check if the feature is not mock-only

## Common Failure Mode

The most common drift pattern in this repo is partial implementation:

- a tool name is documented
- a route exists in one layer
- another layer is missing or disabled

That creates apparent capability without reliable execution.

## Working Rule

Treat new tool work as a stack change, not a single-file change. If a feature does not move through schema, routing, execution, validation, and documentation together, the repo becomes harder for clients and operators to trust.
