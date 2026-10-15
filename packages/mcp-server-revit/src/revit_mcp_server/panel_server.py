"""Loopback-only HTTP shim for the Revit dockable panel (WebView2 JS).

The MCP hub (mcp_server.py) speaks stdio to AI clients (Claude Desktop/Code) —
a browser page in WebView2 cannot launch or speak to a stdio subprocess, so
the panel UI talks HTML/JS to the add-in over the WebView2 message bridge,
and the add-in reaches the hub via localhost. This module runs the *same*
provider registry as the stdio server behind a minimal local-only HTTP
server, so the C# add-in can forward panel button clicks to real MCP tools.

This is not a general-purpose remote API: it binds 127.0.0.1 only, mirroring
every other switch in this product (Revit/Rhino/Navisworks bridges), and
exists purely so a WebView2 page in the same machine's Revit process can
reach the hub.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from . import agent_bridge
from . import agent_native
from .config import config
from .errors import RevitMCPError
from .registry_factory import build_registry
from .security.audit import redact_data
from .security.workspace import WorkspaceMonitor

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8787

# report_generator writes exports directly to the workspace root (see
# modules/report_generator/module.py's _ws_dir). Other modules keep their own
# state there too (qaqc_issues.db, saved_selections.json) - these are never
# something a user exported and would want to open, so they're excluded by
# name even though qaqc_issues.db shares a report extension.
REPORT_EXTENSIONS = {".xlsx", ".csv", ".db"}
NON_REPORT_FILENAMES = {"qaqc_issues.db", "clash_triage.db"}


def _run_tool_sync(registry, approval_provider, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one tool call to completion in a fresh event loop.

    Mirrors the approval-gate check and post-execution plan-state transition
    that mcp_server.py's call_tool() applies, so a tool called through the
    panel is gated identically to one called through MCP.
    """
    async def _run() -> Dict[str, Any]:
        provider = registry.lookup_tool_provider(name)
        if not provider:
            raise ValueError(f"Unknown tool '{name}'")

        tool_def = registry.lookup_tool(name)
        if tool_def and tool_def.is_mutating:
            approval_provider.gate.check_tool_execution(name, arguments)

        result = await provider.execute_tool(name, arguments)

        if tool_def and tool_def.is_mutating and isinstance(arguments, dict) and "plan_id" in arguments:
            try:
                approval_provider.gate.update_plan_state(arguments["plan_id"], "executed")
            except Exception:
                # The tool has already run, so don't fail the call and invite a
                # retry of a completed mutation; make the stale plan visible instead.
                logger.exception(
                    "Tool '%s' executed but plan '%s' could not be marked executed",
                    name,
                    arguments["plan_id"],
                )

        return result

    return asyncio.run(_run())


def collect_diagnostics(workspace_dir: Path) -> Dict[str, Any]:
    """Install-to-first-check status: one entry per thing that can block a first run.

    Each check carries a ``next_step`` so the panel can show a specific recovery
    action instead of a generic connection error.
    """
    from .bridge.discovery import available_host_versions
    from .config import BridgeMode

    checks = []

    def add(check_id: str, ok: bool, detail: str, next_step: str = "") -> None:
        checks.append({"id": check_id, "ok": ok, "detail": detail, "next_step": "" if ok else next_step})

    add("hub", True, "Panel hub is running.")

    if config.mode == BridgeMode.mock:
        add(
            "mode", False,
            "Hub is in mock mode: tools return generated sample data, not your Revit model.",
            "Set MCP_REVIT_MODE=bridge and restart the hub.",
        )
    else:
        add("mode", True, f"Hub mode is '{config.mode.value}'.")
        versions = available_host_versions("revit")
        add(
            "revit_bridge", bool(versions),
            f"Live Revit bridge(s): {', '.join(versions)}." if versions else "No live Revit bridge found.",
            "Open Revit with the AEC Model Bridge add-in loaded and an active project, then refresh. "
            "If Revit is open, check that the add-in matches your Revit version (docs/install.md).",
        )

    try:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        probe = workspace_dir / ".diagnostics-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        add("workspace", True, f"Workspace is writable: {workspace_dir}")
    except OSError as e:
        add(
            "workspace", False, f"Workspace is not writable: {workspace_dir} ({e.strerror or e})",
            "Set MCP_REVIT_WORKSPACE_DIR to a folder you can write to and restart the hub.",
        )

    claude_ok = bool(config.anthropic_api_key) or shutil.which("claude") is not None
    add(
        "ai_provider", claude_ok,
        "An AI provider is available for panel chat." if claude_ok else "No AI provider for panel chat.",
        "Set MCP_REVIT_ANTHROPIC_API_KEY, or install and sign in to the claude CLI, then restart Revit.",
    )

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


class PanelRequestHandler(BaseHTTPRequestHandler):
    registry = None
    approval_provider = None
    workspace = None

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.debug("panel_server: " + format, *args)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorize(self, is_post: bool) -> bool:
        """Reject requests with an unexpected Host, any Origin, or a non-JSON POST.

        The only legitimate caller is the add-in's C# HttpClient, which sends a
        loopback Host and no Origin header. Sends the error response and returns
        False when the request must not proceed. No CORS headers are served and
        OPTIONS is not handled.
        """
        port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in allowed_hosts:
            self._send_json(403, {"ok": False, "error": "Forbidden host"})
            return False
        if self.headers.get("Origin") is not None:
            self._send_json(403, {"ok": False, "error": "Requests with an Origin header are not allowed"})
            return False
        if is_post:
            ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if ctype != "application/json":
                self._send_json(415, {"ok": False, "error": "Content-Type must be application/json"})
                return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorize(is_post=False):
            return
        if self.path == "/health":
            self._send_json(200, {"status": "healthy"})
            return
        if self.path == "/diagnostics":
            self._send_json(200, collect_diagnostics(self.workspace.allowed_directories[0]))
            return
        if self.path == "/reports":
            self._handle_list_reports()
            return
        if self.path == "/agent/providers":
            self._handle_agent_providers()
            return
        self._send_json(404, {"ok": False, "error": f"Unknown path '{self.path}'"})

    def _handle_agent_providers(self) -> None:
        """Reports which chat providers are actually usable right now, so the
        panel's dropdown can show/enable options accordingly. "claude" covers
        both the native (API key) and CLI-fallback paths that /agent/chat's
        dispatch chain below may route to; "codex" has no native path (CLI
        only, per Task 1's ADR)."""
        claude_available = bool(config.anthropic_api_key) or shutil.which("claude") is not None
        codex_available = shutil.which("codex") is not None
        self._send_json(200, {"ok": True, "providers": {"claude": claude_available, "codex": codex_available}})

    def _handle_list_reports(self) -> None:
        workspace_dir = self.workspace.allowed_directories[0]
        reports = [
            {
                "path": str(entry),
                "name": entry.name,
                "modified": entry.stat().st_mtime,
            }
            for entry in workspace_dir.iterdir()
            if entry.is_file()
            and entry.suffix.lower() in REPORT_EXTENSIONS
            and entry.name not in NON_REPORT_FILENAMES
        ]
        reports.sort(key=lambda r: r["modified"], reverse=True)
        self._send_json(200, {"ok": True, "reports": reports})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorize(is_post=True):
            return
        if self.path == "/agent/chat":
            self._handle_agent_chat()
            return

        if self.path != "/execute":
            self._send_json(404, {"ok": False, "error": f"Unknown path '{self.path}'"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Request body must be valid JSON"})
            return

        tool = body.get("tool")
        arguments = body.get("arguments", {})
        if not tool or not isinstance(tool, str):
            self._send_json(400, {"ok": False, "error": "Request body must include a string 'tool' field"})
            return

        try:
            result = _run_tool_sync(self.registry, self.approval_provider, tool, arguments)
            self._send_json(200, {"ok": True, "result": redact_data(result)})
        except RevitMCPError as e:
            self._send_json(409, {"ok": False, "error": redact_data(str(e))})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": redact_data(str(e))})

    def _handle_agent_chat(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Request body must be valid JSON"})
            return

        message = body.get("message")
        if not message or not isinstance(message, str):
            self._send_json(400, {"ok": False, "error": "Request body must include a string 'message' field"})
            return

        provider = body.get("provider") or "claude"
        session_id = body.get("session_id")

        try:
            if provider == "codex":
                # codex has no native path (Task 1's ADR scopes it as
                # CLI-only) - route here unconditionally, even when an API
                # key is configured for the "claude" native path. agent_bridge
                # itself reports a missing-CLI error if codex isn't on PATH.
                result = agent_bridge.run_agent_turn(provider, message, session_id)
            elif config.anthropic_api_key:
                # Native path takes priority for "claude" (or an unspecified
                # provider, which defaults to "claude") whenever an API key
                # is configured - it replaces the CLI-based "claude" option
                # entirely (see /agent/providers above for how the panel
                # learns this).
                result = agent_native.run_native_turn(message, session_id, self.registry, self.approval_provider)
            elif provider == "claude" and shutil.which("claude") is not None:
                # CLI fallback: only reached with no API key configured AND
                # the claude CLI resolvable on PATH.
                result = agent_bridge.run_agent_turn(provider, message, session_id)
            else:
                result = {
                    "ok": False,
                    "error": (
                        "No AI provider is available. Set the MCP_REVIT_ANTHROPIC_API_KEY "
                        "environment variable and restart Revit, or install and sign in "
                        "to the claude/codex CLI."
                    ),
                }
        except Exception as e:
            self._send_json(500, {"ok": False, "error": redact_data(str(e))})
            return

        if not result.get("ok"):
            result["error"] = redact_data(result.get("error", ""))
        self._send_json(200 if result.get("ok") else 502, result)


def build_server(port: int | None = None, workspace: WorkspaceMonitor | None = None) -> ThreadingHTTPServer:
    registry, approval_provider, _job_manager, _module_registry, resolved_workspace = build_registry(workspace=workspace)

    handler = type("BoundPanelRequestHandler", (PanelRequestHandler,), {
        "registry": registry,
        "approval_provider": approval_provider,
        "workspace": resolved_workspace,
    })

    resolved_port = port if port is not None else int(os.getenv("MCP_PANEL_HTTP_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer(("127.0.0.1", resolved_port), handler)
    return server


def default_log_path() -> Path:
    """``%APPDATA%/AECModelBridge/Logs/panel-hub.log``, beside the add-in's bridge.jsonl."""
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".local" / "share"
    return base / "AECModelBridge" / "Logs" / "panel-hub.log"


def configure_file_logging(log_path: Path | None = None) -> Path | None:
    """Persist hub logs to a rotating file.

    The add-in launches the hub without capturing stdout/stderr, so without a
    file handler failures such as a stale plan state would be invisible.
    Returns the log path, or None if the file could not be opened (logging to a
    file must never stop the hub from starting).
    """
    path = log_path or default_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        logger.warning("Could not open panel hub log file %s", path, exc_info=True)
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    package_logger = logging.getLogger(__name__.rsplit(".", 1)[0])
    package_logger.addHandler(handler)
    if package_logger.getEffectiveLevel() > logging.INFO:
        package_logger.setLevel(logging.INFO)
    return path


def run_panel_server() -> None:
    """Entry point for running the panel HTTP shim as a standalone process."""
    configure_file_logging()
    server = build_server()
    logger.info("Panel HTTP shim listening on http://127.0.0.1:%d", server.server_address[1])
    try:
        server.serve_forever()
    finally:
        server.shutdown()


if __name__ == "__main__":
    run_panel_server()
