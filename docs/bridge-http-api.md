# Bridge HTTP API

The Revit add-in exposes a localhost HTTP listener implemented in [BridgeServer.cs](../packages/revit-bridge-addin/src/Bridge/BridgeServer.cs).

## Default Binding

The bridge server binds to:

- `http://127.0.0.1:3000/`

This default is hard-coded in the `BridgeServer` constructor unless a different prefix is passed at startup.

## Supported Endpoints

### `GET /health`

Returns basic bridge health metadata, including:

- `status`
- assembly `version`
- `uptime_seconds`
- detected `revit_version`
- `active_document`

This is the fastest way to confirm the add-in loaded and the listener is reachable.

### `GET /tools`

Returns the tool catalog built by `BridgeCommandFactory.GetToolCatalog()`.

Use this endpoint when you want to verify what the C# layer currently advertises, rather than relying only on top-level documentation.

### `POST /execute`

Executes a routed Revit command.

Expected JSON shape:

```json
{
  "request_id": "req-123",
  "tool": "revit.health",
  "payload": {
    "request_id": "req-123"
  }
}
```

Operational details:

- the request body is parsed as JSON
- the tool name is routed through `BridgeCommandFactory`
- the request is queued into `CommandQueue`
- `ExternalEvent.Raise()` hands execution to the Revit UI thread
- the HTTP response waits for queue completion or timeout

## Response Model

Bridge responses are serialized from `CommandResponse`:

- `status`
- `tool`
- `result`
- optional `message`
- optional `stack_trace`

Timeout handling is implemented in `CommandQueue.WaitForResponse()` with a default 30 second limit.

## Error Semantics

Unknown routes return `404`.

Unhandled exceptions inside request processing return `500` with a JSON error object. Command execution exceptions are converted into `CommandResponse` objects with `status = "error"`.

## Operational Rule

Treat `/health` and `/tools` as diagnostics, and `/execute` as the only mutation-capable entrypoint. If you are debugging live automation, check `/health` first before assuming a tool-routing problem.
