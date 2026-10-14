"""Read-only session tools for the Revit provider: where am I (revit_get_context) and what became of an
earlier call that outlived the wait (revit_get_result)."""
from __future__ import annotations

from importlib import metadata
from typing import Any

from ..errors import BridgeError
from .base import ProviderTool

CONTEXT_WAIT_SECONDS = 3.0
_NOT_IN_CATALOG = "not available in bridge"

CONTEXT_TOOLS = [
    ProviderTool(
        name="revit_get_context",
        description=(
            "Read-only snapshot of the live Revit session: which build of the add-in is loaded (and whether it matches "
            "this server), Revit version, active document (title, path, guid, workshared), active view, how many "
            "requests are queued, which request is running and for how long, and the approval mode. Call it first in a "
            "session and after any restart. Needs no approval. A stale add-in that predates this tool is reported, not an error."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    ProviderTool(
        name="revit_get_result",
        description=(
            "Collect the outcome of an earlier Revit call that returned status 'running' with a request_id. Waits up to "
            "wait_s seconds, then returns the real output, the failure, or 'running' again. Results are kept by the "
            "add-in for about 15 minutes. Read-only; never re-runs anything."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "The request_id from the 'running' result."},
                "wait_s": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 25,
                    "description": "Seconds to wait for it to finish before answering 'running' again. Default 25.",
                },
            },
            "required": ["request_id"],
        },
    ),
]


def _server_version() -> str | None:
    try:
        return metadata.version("aec-model-bridge")
    except metadata.PackageNotFoundError:
        return None


def _call_quick(bridge: Any, command: str) -> dict[str, Any]:
    call = getattr(bridge, "call_tool", None)
    if call is not None:
        return call(command, {}, wait_s=CONTEXT_WAIT_SECONDS)
    return bridge.send_tool(command, {})


def get_context(bridge: Any, *, live: bool, approval_mode: str) -> dict[str, Any]:
    """Merge the add-in's unqueued /health (queue, running job, build) with its revit.get_context command.

    /health is answered on the HTTP thread, so it still works while Revit is busy with a long script;
    the command needs the Revit thread and may only report 'running' in that case.
    """
    server = {"version": _server_version(), "approval_mode": approval_mode}
    if not live:
        return {
            "ok": True,
            "mock": True,
            "tool": "revit_get_context",
            "server": server,
            "message": "Mock mode: there is no Revit session. Nothing here describes a real model.",
        }

    warnings: list[str] = []
    health: dict[str, Any] = {}
    try:
        health = bridge._get("/health") if hasattr(bridge, "_get") else {}
    except Exception as exc:
        warnings.append(f"Could not read /health: {exc}")

    command: dict[str, Any] = {}
    supports_context = True
    busy = False
    try:
        command = _call_quick(bridge, "revit.get_context")
        if command.get("status") == "running":
            busy = True
            command = {}
            warnings.append(
                "Revit is busy with another request, so document and view details are unavailable right now. "
                "Try again when 'running' below is empty."
            )
    except BridgeError as exc:
        if _NOT_IN_CATALOG not in str(exc):
            raise
        supports_context = False
        warnings.append(
            "The loaded add-in has no revit.get_context command, so it is older than this server. "
            "Rebuild and reinstall the add-in, then restart Revit."
        )

    queue = dict(command.get("queue") or {})
    if "queue_depth" in health:
        queue["depth"] = health["queue_depth"]
    if "retained_results" in health:
        queue["retained_results"] = health["retained_results"]
    queue["running"] = health.get("running")

    addin = command.get("addin") or health.get("build") or {"version": health.get("version")}
    addin_version = addin.get("version") if isinstance(addin, dict) else None
    if addin_version and server["version"] and str(addin_version) != str(server["version"]).split("+")[0]:
        warnings.append(f"Add-in {addin_version} and server {server['version']} differ in version; one of them is stale.")

    return {
        "ok": True,
        "tool": "revit_get_context",
        "server": server,
        "addin": addin,
        "addin_supports_context": supports_context,
        "revit": command.get("revit") or {"version": health.get("revit_version")},
        "document": command.get("document") if command else None,
        "active_document": health.get("active_document"),
        "queue": queue,
        "busy": busy,
        "warnings": warnings,
    }


def get_result(bridge: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    request_id = arguments.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id is required")
    fetch = getattr(bridge, "get_result", None)
    if fetch is None:
        raise ValueError("This bridge cannot look up earlier requests.")
    wait_s = arguments.get("wait_s")
    return fetch(request_id.strip(), wait_s=wait_s)
