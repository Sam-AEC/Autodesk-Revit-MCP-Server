# Revit Add-in Lifecycle

The Revit-side runtime starts in [packages/revit-bridge-addin/src/Bridge/App.cs](../packages/revit-bridge-addin/src/Bridge/App.cs).

## Startup Path

`App` implements `IExternalApplication`, so Revit calls:

- `OnStartup()`
- `OnShutdown()`

During `OnStartup()` the add-in:

1. initializes Serilog file logging
2. captures the running Revit version
3. creates a shared `CommandQueue`
4. creates `RevitCommandExecutor` and wraps it in `ExternalEvent`
5. constructs and starts `BridgeServer`
6. builds the ribbon UI
7. hooks `DocumentChanged` to keep `ActiveDocumentName` updated

This is the full bootstrap chain that makes the localhost bridge usable.

## Queue And UI Thread Handoff

The important separation is:

- `BridgeServer` receives HTTP requests off the Revit UI thread
- `CommandQueue` stores pending requests and completion handles
- `ExternalEvent.Raise()` transfers execution to `RevitCommandExecutor`
- `RevitCommandExecutor.Execute()` drains the queue on the Revit API thread

That pattern is what makes live Revit automation safe inside Autodesk's threading model.

## Ribbon Surface

`CreateModernRibbonInterface()` creates:

- a `RevitMCP` tab
- a `Connection` panel
- a `Tools` panel

It wires button commands for:

- connect
- disconnect
- status
- settings
- help

The ribbon is more than cosmetic: it exposes operational status and provides a manual control surface for the bridge lifecycle.

## Runtime State

`App` keeps a few static values available to the rest of the add-in:

- `RevitVersion`
- `ActiveDocumentName`
- `Server`

Those values are used indirectly by the health endpoint and operator diagnostics.

## Shutdown Path

`OnShutdown()`:

- stops the bridge server
- disposes the `ExternalEvent`
- flushes logs

If shutdown errors occur, they are logged and returned as `Result.Failed`.

## Operational Rule

If the bridge looks healthy from the Python side but tools still do nothing, inspect the add-in lifecycle first. Most hard failures in this repo start before tool routing, during startup, ribbon initialization, or `ExternalEvent` creation.
