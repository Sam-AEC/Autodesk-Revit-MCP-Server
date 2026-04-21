# Tool Registry Phases

The main routing surface for live Revit commands is [BridgeCommandFactory.cs](../packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs).

## Why This File Matters

`BridgeCommandFactory` does two jobs:

- routes inbound `tool` names to execution methods
- publishes the bridge-side tool catalog through `GetToolCatalog()`

That makes it the practical source of truth for what the add-in can actually expose at runtime.

## Batch-Based Growth

The file is organized in functional batches rather than a single flat tool list.

Observed batch themes include:

- original health and document tools
- document management
- geometry creation
- component placement
- view creation
- parameters and properties
- sheets and documentation
- advanced exports
- selection and annotation
- structure and MEP
- editing and worksharing
- groups, links, phases, and design options
- universal reflection access
- LLM-oriented power tools such as `execute_python`

This structure is helpful because it shows how the tool surface expanded over time.

## Catalog Drift Risk

The file also contains several important signals that operators should not ignore:

- some tools are commented out in the execution switch
- some tools still appear in `GetToolCatalog()`
- the `.csproj` currently removes broad command directories from compilation

That means three different states can exist at once:

1. source file exists
2. tool name appears in catalog
3. compiled add-in actually executes the implementation

Those states are not guaranteed to match.

## Practical Consequence

If a client sees a tool in documentation or even in `/tools`, that does not automatically guarantee the compiled binary can execute the full command path without compatibility issues.

Examples of temporary compatibility comments already appear in the registry around:

- cable tray
- MEP systems
- render settings
- revision cloud
- text type
- room boundary
- project location

## Working Rule

When adding or enabling a tool, update all three layers together:

- execution switch
- advertised catalog
- build or compilation status

If only one layer changes, this repo becomes harder to reason about and clients will overestimate what the bridge can do.
