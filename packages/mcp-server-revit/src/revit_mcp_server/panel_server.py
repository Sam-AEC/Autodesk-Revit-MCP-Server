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
import collections
import contextlib
import hmac
import json
import logging
import os
import shutil
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from . import agent_bridge
from . import agent_native
from .config import config
from .errors import RevitMCPError
from .registry_factory import build_registry
from .security.approval import HUMAN_ONLY_TOOLS
from .security.proof import panel_plans_redacted
from .security.audit import redact_data, redact_for_approval, redact_known_secrets, register_secret_value
from .security.dispatch import run_gated_tool
from .security.dev_mode import set_panel_mode
from .security.panel_token import TOKEN_HEADER, PanelTokenError, load_or_create_token, read_token
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


# (plan_actions is NOT here: it reads before-values from Revit, so it must be routed or refused like
# any tool that reaches Revit.)
# Tools that only touch the hub's own plan files and never call a Revit bridge. With several
# Revits open they do not need an `instance`; everything else does (see resolve_instance).
HUB_LOCAL_TOOLS = frozenset({"list_pending_plans", "approve_plan", "reject_plan", "get_proof_bundle"})

MAX_BODY_BYTES = 1_048_576
MAX_TOKEN_HEADER_CHARS = 256
FAILURE_LIMIT = 20
FAILURE_WINDOW_SECONDS = 60.0


class InstanceRoutingError(Exception):
    """The request cannot be routed to exactly one Revit. The message is safe to show."""


class FailureLimiter:
    """Light cap on failed token checks (default 20 per minute per process).

    It only throttles *failures*: a request with the right token is never counted or
    limited, so an attacker spraying bad tokens cannot lock the real panel out. Over the
    limit, a bad request is answered 429 without further work or logging.
    """

    def __init__(self, limit: int = FAILURE_LIMIT, window: float = FAILURE_WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window
        self._events: collections.deque = collections.deque(maxlen=limit + 1)
        self._lock = threading.Lock()

    def record_failure(self) -> bool:
        """Record a failed attempt. Returns False once the limit for the window is exceeded."""
        now = time.monotonic()
        with self._lock:
            while self._events and now - self._events[0] > self.window:
                self._events.popleft()
            self._events.append(now)
            return len(self._events) <= self.limit


def _describe_instances(switches) -> str:
    return "; ".join(
        f"pid {s.pid} (Revit {s.host_version}, started {s.started_at})" for s in switches
    ) or "none"


def resolve_instance(instance: Any, tool: str):
    """Pick the Revit bridge a request should act on, from the live bridge registry.

    ``instance`` is ``{"pid": <Revit process id>, "document": <title, informational>}``, sent
    by the add-in that hosts the panel. Rules:

    * Mock mode, or an explicit MCP_REVIT_BRIDGE_URL: no routing (returns None).
    * Hub-local tools with no ``instance``: no routing (they never reach Revit).
    * ``instance`` given: must match a live registry entry by pid, else an error listing the
      live instances. The registry decides the endpoint and token, never the request.
    * No ``instance``: the single live instance; no live instance returns None (the provider
      reports "no bridge"); two or more is refused rather than guessed.

    The document title is not in the registry, so it is carried for messages only and is
    not used to match. A pid alone can be reused by Windows; that is the open item in
    docs/0014-multi-revit-routing.md.
    """
    from .config import BridgeMode
    from .bridge import discovery

    if config.mode != BridgeMode.bridge or config.bridge_url:
        return None
    pid = None
    if instance is not None:
        raw_pid = instance.get("pid") if isinstance(instance, dict) else None
        if isinstance(raw_pid, bool) or not isinstance(raw_pid, int):
            raise InstanceRoutingError("'instance' must be an object with an integer 'pid' (the Revit process id).")
        pid = raw_pid
    elif tool in HUB_LOCAL_TOOLS:
        return None

    live = [s for s in discovery.discover_switch_list(prune=False) if s.provider_id == "revit"]
    if pid is not None:
        for switch in live:
            if switch.pid == pid:
                return switch
        raise InstanceRoutingError(
            f"No live Revit bridge for process {pid}. Live Revit instances: {_describe_instances(live)}. "
            "Reopen the panel from that Revit, or restart it."
        )
    if len(live) > 1:
        raise InstanceRoutingError(
            "More than one Revit is open and the request did not say which one. "
            f"Live Revit instances: {_describe_instances(live)}. "
            "Use the panel in the Revit you mean, or close the others."
        )
    return live[0] if live else None


def _route(registry, switch):
    if switch is None:
        return contextlib.nullcontext()
    provider = registry.get_provider("revit")
    if provider is None or not hasattr(provider, "routed_to"):
        return contextlib.nullcontext()
    return provider.routed_to(switch.endpoint, switch.session_token)


def _run_tool_sync(registry, approval_provider, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one tool call to completion in a fresh event loop.

    Mirrors the approval-gate check and post-execution plan-state transition
    that mcp_server.py's call_tool() applies, so a tool called through the
    panel is gated identically to one called through MCP.
    """
    async def _run() -> Dict[str, Any]:
        if name in HUMAN_ONLY_TOOLS:
            # The panel's Plans view: the channel is recorded as 'panel' by this route,
            # never taken from the request. See docs/security.md for what this route
            # does not authenticate.
            return await approval_provider.execute_human_tool(name, arguments, via="panel")
        return await run_gated_tool(registry, approval_provider.gate, name, arguments)

    return asyncio.run(_run())


APPROVAL_MODE_NOTES = {
    "look_only": "Look only: I read, never change the model.",
    "ask_first": "Ask me first: changes need your approval in this panel.",
    "auto": "Auto: approvals are skipped. Not recommended.",
}


def collect_diagnostics(workspace_dir: Path, approval_mode: Any = None, auto_window: Any = None,
                        dev_mode: bool = False) -> Dict[str, Any]:
    """Install-to-first-check status: one entry per thing that can block a first run.

    Each check carries a ``next_step`` so the panel can show a specific recovery
    action instead of a generic connection error.
    """
    from .bridge.discovery import available_host_versions
    from .config import BridgeMode, normalize_approval_mode

    mode_value = normalize_approval_mode(config.approval_mode if approval_mode is None else approval_mode)
    dev_mode = bool(dev_mode and mode_value == "auto")
    mode_note = "Dev mode: approvals are skipped until you switch it off. Calls are audited." if dev_mode else APPROVAL_MODE_NOTES[mode_value]
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
        versions = available_host_versions("revit", prune=False)
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

    add(
        "approval_mode", mode_value != "auto", mode_note,
        "Set approval_mode to ask_first (or look_only) so changes need your approval, then restart the hub.",
    )

    return {
        "ok": all(c["ok"] for c in checks),
        "approval_mode": mode_value,
        "approval_mode_note": mode_note,
        "dev_mode": dev_mode,
        "auto_expires_at": auto_window["expires_at"] if not dev_mode and mode_value == "auto" and isinstance(auto_window, dict) else None,
        "checks": checks,
    }


class PanelRequestHandler(BaseHTTPRequestHandler):
    registry = None
    approval_provider = None
    workspace = None
    token: str | None = None
    failures: FailureLimiter | None = None
    _stale_logged = False

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.debug("panel_server: " + format, *args)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        try:
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
        except ValueError:
            status = 500
            body = json.dumps({"ok": False, "error": "The response held a number that is not valid JSON."}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reject(self, status: int, error: str) -> bool:
        """Send an error and return False. Reads (a bounded amount of) the request
        body first: closing a socket with unread data makes Windows send a reset
        that can destroy the response before the client reads it."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if 0 < length <= 1_048_576:
            try:
                self.rfile.read(length)
            except OSError:
                pass
        self._send_json(status, {"ok": False, "error": error})
        return False

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
            return self._reject(403, "Forbidden host")
        if self.headers.get("Origin") is not None:
            return self._reject(403, "Requests with an Origin header are not allowed")
        if is_post:
            ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if ctype != "application/json":
                return self._reject(415, "Content-Type must be application/json")
        return True

    def _check_token(self) -> bool:
        """Require the per-user token (header X-AMB-Token) with a constant-time compare.

        The response never says whether the header was missing or wrong. A hub with no token
        configured refuses everything (fail closed).
        """
        expected = self.token or ""
        supplied = self.headers.get(TOKEN_HEADER) or ""
        ok = bool(expected) and 0 < len(supplied) <= MAX_TOKEN_HEADER_CHARS and hmac.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        )
        if ok:
            return True
        limiter = self.failures
        if limiter is not None and not limiter.record_failure():
            return self._reject(429, "Too many failed requests")
        self._warn_if_token_file_changed()
        return self._reject(401, "Unauthorized")

    def _warn_if_token_file_changed(self) -> None:
        """Log (once, without any token text) when the token file no longer matches this hub."""
        cls = type(self)
        if cls._stale_logged or not self.token:
            return
        try:
            on_disk = read_token()
        except PanelTokenError:
            on_disk = None
        if on_disk is not None and not hmac.compare_digest(on_disk.encode(), self.token.encode()):
            cls._stale_logged = True
            logger.warning(
                "The panel token file changed after this hub started. Restart the hub so it uses the new token."
            )

    def _read_body(self) -> bytes | None:
        """Read the request body (bounded). Sends 400/413 and returns None when it is unusable."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            self._send_json(400, {"ok": False, "error": "Invalid Content-Length"})
            return None
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"ok": False, "error": "Request body too large"})
            return None
        return self.rfile.read(length) if length else b"{}"

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorize(is_post=False):
            return
        if self.path == "/health":
            self._send_json(200, {"status": "healthy"})
            return
        if not self._check_token():
            return
        if self.path == "/diagnostics":
            gate = getattr(self.approval_provider, "gate", None)
            self._send_json(200, collect_diagnostics(
                    self.workspace.allowed_directories[0],
                    getattr(gate, "approval_mode", None) if gate is not None else getattr(self.approval_provider, "approval_mode", None),
                    gate.auto_window() if gate is not None and hasattr(gate, "auto_window") else None,
                    bool(getattr(gate, "dev_mode", False)),
                ),
            )
            return
        if self.path == "/reports":
            self._handle_list_reports()
            return
        if self.path == "/agent/providers":
            self._handle_agent_providers()
            return
        self._send_json(404, {"ok": False, "error": f"Unknown path '{self.path}'"})

    def _handle_set_approval_mode(self) -> None:
        """Authenticated panel switch for timed Auto, persistent Dev, or Ask first.
        Enabling either override requires confirm:true; look_only is never relaxed."""
        raw = self._read_body()
        if raw is None:
            return
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = None
        if not isinstance(body, dict):
            self._send_json(400, {"ok": False, "error": "Request body must be a JSON object"})
            return

        gate = self.approval_provider.gate
        mode = body.get("mode")
        if mode in ("auto", "dev"):
            if gate.baseline_approval_mode == "look_only":
                self._send_json(409, {"ok": False, "error": "Approvals are locked to look-only for this hub; "
                                      "the panel cannot relax them."})
                return
            if body.get("confirm") is not True:
                self._send_json(400, {"ok": False, "error": "Switching to Auto or Dev needs an explicit confirmation."})
                return
            if mode == "dev" and set(body) - {"mode", "confirm"}:
                self._send_json(400, {"ok": False, "error": "Dev accepts only mode and confirm; filesystem scope is unchanged."})
                return
            try:
                set_panel_mode(gate.workspace_dir, mode, token=self.token or "", minutes=body.get("minutes"))
            except (OSError, RevitMCPError, PanelTokenError) as e:
                self._send_json(500, {"ok": False, "error": redact_data(f"Could not save the approval mode: {e}")})
                return
            logger.warning("Approval mode switched to %s from the panel (expires %s)",
                           mode.upper(), (gate.auto_window() or {}).get("expires_at"))
        elif mode in ("ask_first", "required"):
            try:
                set_panel_mode(gate.workspace_dir, mode, token=self.token or "")
            except OSError as e:
                self._send_json(500, {"ok": False, "error": redact_data(f"Could not save the approval mode: {e}")})
                return
            logger.info("Approval mode set back to ask_first from the panel")
        else:
            self._send_json(400, {"ok": False, "error": "mode must be 'auto', 'dev' or 'ask_first'"})
            return

        self._send_json(200, collect_diagnostics(gate.workspace_dir, gate.approval_mode, gate.auto_window(), gate.dev_mode))

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
        if not self._check_token():
            return
        if self.path == "/agent/chat":
            self._handle_agent_chat()
            return
        if self.path == "/approval-mode":
            self._handle_set_approval_mode()
            return

        if self.path != "/execute":
            self._send_json(404, {"ok": False, "error": f"Unknown path '{self.path}'"})
            return

        raw = self._read_body()
        if raw is None:
            return
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Request body must be valid JSON"})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"ok": False, "error": "Request body must be a JSON object"})
            return

        tool = body.get("tool")
        arguments = body.get("arguments", {})
        if not tool or not isinstance(tool, str):
            self._send_json(400, {"ok": False, "error": "Request body must include a string 'tool' field"})
            return

        try:
            switch = resolve_instance(body.get("instance"), tool)
        except InstanceRoutingError as e:
            self._send_json(409, {"ok": False, "error": str(e)})
            return

        try:
            with _route(self.registry, switch):
                result = _run_tool_sync(self.registry, self.approval_provider, tool, arguments)
            if tool == "list_pending_plans":
                # Fail closed if redaction would change what the person approves.
                result = panel_plans_redacted(result, redact_data, redact_for_approval)
            else:
                result = redact_data(result)
            self._send_json(200, {"ok": True, "result": result})
        except RevitMCPError as e:
            self._send_json(409, {"ok": False, "error": redact_data(str(e))})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": redact_data(str(e))})

    def _handle_agent_chat(self) -> None:
        raw = self._read_body()
        if raw is None:
            return
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Request body must be valid JSON"})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"ok": False, "error": "Request body must be a JSON object"})
            return

        message = body.get("message")
        if not message or not isinstance(message, str):
            self._send_json(400, {"ok": False, "error": "Request body must include a string 'message' field"})
            return

        provider = body.get("provider") or "claude"
        session_id = body.get("session_id")

        try:
            switch = resolve_instance(body.get("instance"), "agent_chat")
        except InstanceRoutingError as e:
            self._send_json(409, {"ok": False, "error": str(e)})
            return
        uses_cli = provider == "codex" or not config.anthropic_api_key
        if uses_cli:
            # The CLI starts its own MCP server process, which picks the newest Revit and cannot
            # be pinned yet (docs/0014-multi-revit-routing.md, problem 4). Refuse rather than guess.
            from .bridge import discovery
            from .config import BridgeMode

            live = [s for s in discovery.discover_switch_list(prune=False) if s.provider_id == "revit"]
            if config.mode == BridgeMode.bridge and not config.bridge_url and len(live) > 1:
                self._send_json(409, {"ok": False, "error": (
                    "More than one Revit is open, and chat through the claude/codex CLI cannot be pinned to one yet. "
                    f"Live Revit instances: {_describe_instances(live)}. Close the others, or set "
                    "MCP_REVIT_ANTHROPIC_API_KEY to use the built-in assistant."
                )})
                return

        try:
            with _route(self.registry, switch):
                result = self._dispatch_chat(provider, message, session_id)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": redact_data(str(e))})
            return

        if not result.get("ok"):
            result["error"] = redact_data(result.get("error", ""))
        self._send_json(200 if result.get("ok") else 502, result)

    def _dispatch_chat(self, provider: str, message: str, session_id: Any) -> Dict[str, Any]:
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
        return result


def build_server(
    port: int | None = None,
    workspace: WorkspaceMonitor | None = None,
    token: str | None = None,
) -> ThreadingHTTPServer:
    """Build the hub. ``token`` defaults to the per-user token file (created if this is the first
    hub to start); raises PanelTokenError if that file is unsafe. A hub never runs without a token."""
    resolved_token = token if token is not None else load_or_create_token()
    if not resolved_token:
        raise PanelTokenError("The panel hub needs an access token.")
    register_secret_value(resolved_token)
    registry, approval_provider, _job_manager, _module_registry, resolved_workspace = build_registry(workspace=workspace)

    handler = type("BoundPanelRequestHandler", (PanelRequestHandler,), {
        "registry": registry,
        "approval_provider": approval_provider,
        "workspace": resolved_workspace,
        "token": resolved_token,
        "failures": FailureLimiter(),
        "_stale_logged": False,
    })

    resolved_port = port if port is not None else int(os.getenv("MCP_PANEL_HTTP_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer(("127.0.0.1", resolved_port), handler)
    return server


def default_log_path() -> Path:
    """``%APPDATA%/AECModelBridge/Logs/panel-hub.log``, beside the add-in's bridge.jsonl."""
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".local" / "share"
    return base / "AECModelBridge" / "Logs" / "panel-hub.log"


def _mask_known_secrets(record: logging.LogRecord) -> bool:
    """Defence in depth: nothing should log the hub token, but if it ever did the file would not keep it."""
    try:
        text = record.getMessage()
    except Exception:
        return True
    masked = redact_known_secrets(text)
    if masked != text:
        record.msg, record.args = masked, None
    return True


class _RedactingFormatter(logging.Formatter):
    """Wraps another formatter and masks known secrets in the whole formatted line, tracebacks included."""

    def __init__(self, inner: logging.Formatter | None = None) -> None:
        super().__init__()
        self._inner = inner or logging.Formatter()

    def format(self, record: logging.LogRecord) -> str:
        return redact_known_secrets(self._inner.format(record))


def mask_secrets_on_all_handlers() -> None:
    """Install the redacting formatter on every handler of the package and root loggers (console too)."""
    for lg in (logging.getLogger(__name__.rsplit(".", 1)[0]), logging.getLogger()):
        for h in lg.handlers:
            if not isinstance(h.formatter, _RedactingFormatter):
                h.setFormatter(_RedactingFormatter(h.formatter))


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
    handler.addFilter(_mask_known_secrets)
    handler.setFormatter(_RedactingFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")))
    package_logger = logging.getLogger(__name__.rsplit(".", 1)[0])
    package_logger.addHandler(handler)
    if package_logger.getEffectiveLevel() > logging.INFO:
        package_logger.setLevel(logging.INFO)
    return path


def run_panel_server() -> None:
    """Entry point for running the panel HTTP shim as a standalone process."""
    configure_file_logging()
    try:
        server = build_server()
        mask_secrets_on_all_handlers()
    except PanelTokenError as e:
        logger.error("Panel hub not started: %s", e)
        raise SystemExit(f"Panel hub not started: {e}") from None
    logger.info("Panel HTTP shim listening on http://127.0.0.1:%d", server.server_address[1])
    try:
        server.serve_forever()
    finally:
        server.shutdown()


if __name__ == "__main__":
    run_panel_server()
