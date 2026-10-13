"""Shells out to an already-installed AI coding CLI (Claude Code, Codex) so the
Revit dockable panel can have a real chat surface without this hub reimplementing
an LLM agent loop, tool-calling, or a model provider SDK.

Both CLIs already speak MCP as clients. This hub already speaks MCP as a stdio
server (mcp_server.py). So a chat turn is: launch the CLI non-interactively,
point it at this same server via its own MCP-client config, capture its final
reply. The CLI owns the model call, the tool-calling loop, and (for Claude)
permission handling; this module only owns process plumbing and provider
dispatch. Mutating Revit tool calls still pass through ApprovalGate exactly as
they do for every other caller — nothing here bypasses that.

Personal-use scope only: this assumes the operator's own machine has `claude`
and/or `codex` on PATH and already authenticated. Shipping this to other users
would need a very different trust model (bundled/managed CLI, no reliance on
the operator's own CLI session) — do not extend this to the general product
surface without revisiting that.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any, Dict, Optional

from .config import config
from .security.approval import HUMAN_ONLY_TOOLS

logger = logging.getLogger(__name__)

_TURN_TIMEOUT_SECONDS = 180
_MCP_SERVER_NAME = "aec-model-bridge"
_CODEX_REGISTRATION_CHECKED = False


def _mcp_server_command() -> list[str]:
    """The exact launch command every switch already uses for this hub's stdio
    server, so the CLI's own MCP session and a stdio MCP client see the same
    process shape (mirrors PanelHubLauncher.cs's `python -m revit_mcp_server...`).

    Deliberately the bare "python" on PATH, not sys.executable: verified live
    that passing this process's own sys.executable (a WindowsApps App
    Execution Alias full path) as the command silently fails to hand the CLI
    working MCP tools, while the same bare command resolved via PATH by the
    CLI's own child-process spawner works every time. Matches
    PanelHubLauncher.cs's own bare "python"/"py" convention (see its docstring
    on D-010) rather than inventing a different resolution strategy here."""
    return ["python", "-m", "revit_mcp_server.mcp_server"]


def _neutral_cwd() -> str:
    """Folder the CLI (and the MCP server it starts) runs in.

    Never the hub's own working directory: when that was the bundled Python folder the CLI's
    `python -m revit_mcp_server.mcp_server` picked up that folder's python311.dll and extension
    modules ("Module use of python311.dll conflicts"), the MCP server failed to start, and the
    model answered without any Revit tools. The workspace is a plain, writable folder that holds
    no interpreter files; the temp folder is the fallback."""
    try:
        candidate = config.workspace_dir
        candidate.mkdir(parents=True, exist_ok=True)
        return str(candidate)
    except OSError:
        return tempfile.gettempdir()


def run_agent_turn(provider: str, message: str, session_id: Optional[str]) -> Dict[str, Any]:
    """Runs one chat turn against the requested CLI provider.

    Returns {"ok": True, "response": str, "session_id": str} on success, or
    {"ok": False, "error": str} — never raises for expected failure modes
    (missing CLI, timeout, non-zero exit) so panel_server.py can pass this
    straight through as the response body.
    """
    if provider == "claude":
        return _run_claude_turn(message, session_id)
    if provider == "codex":
        return _run_codex_turn(message, session_id)
    return {"ok": False, "error": f"Unknown agent provider '{provider}' (expected 'claude' or 'codex')"}


def _run_claude_turn(message: str, session_id: Optional[str]) -> Dict[str, Any]:
    # subprocess.run (no shell) resolves a bare name via CreateProcess, which
    # does not search PATHEXT for .cmd/.bat shims the way shutil.which (and a
    # real shell) do. claude.EXE happens to work bare; resolving explicitly
    # here makes that not matter, and fixes the exact failure hit live with
    # codex's npm-installed codex.CMD shim below.
    claude_path = shutil.which("claude")
    if claude_path is None:
        return {"ok": False, "error": "'claude' CLI not found on PATH. Install Claude Code and sign in first."}

    resolved_session_id = session_id or str(uuid.uuid4())
    mcp_config = json.dumps({
        "mcpServers": {
            _MCP_SERVER_NAME: {
                "command": _mcp_server_command()[0],
                "args": _mcp_server_command()[1:],
            }
        }
    })

    args = [
        claude_path, "-p", message,
        "--mcp-config", mcp_config,
        "--strict-mcp-config",
        # Disable Claude Code's own built-in tools (Bash/Edit/Read/...) so this
        # chat surface can only ever touch Revit through the MCP tools above —
        # it should not become a general-purpose shell into the user's machine.
        "--tools", "",
        # --permission-mode only covers Claude Code's own built-in tools (Edit,
        # Bash, ...) — it does NOT auto-approve MCP tool calls. Without an
        # explicit grant, a headless run (no TTY to answer a permission prompt)
        # silently blocks every MCP tool call, and the model may report a
        # plausible-looking fake result instead of the block (verified against
        # a live `claude -p` run). --allowedTools scoped to just this MCP
        # server is what actually lets Revit tool calls proceed; ApprovalGate
        # on the Revit side is still the real safety boundary for mutations.
        "--allowedTools", f"mcp__{_MCP_SERVER_NAME}",
        # Plans are approved by a person (panel or command line), never by the
        # model. The server also hides and refuses these; this is belt and braces.
        "--disallowedTools", *[f"mcp__{_MCP_SERVER_NAME}__{t}" for t in sorted(HUMAN_ONLY_TOOLS)],
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
    ]
    args += ["--resume", resolved_session_id] if session_id else ["--session-id", resolved_session_id]

    # mcp_server.py takes ~2s just to import (Speckle/APS client init etc.) —
    # verified live that without raising MCP_TIMEOUT, Claude Code sometimes
    # gives up waiting for the MCP handshake and silently proceeds with no
    # Revit tools at all, and the model then fabricates a plausible-looking
    # answer instead of reporting that. 30s is comfortably above the observed
    # worst case.
    env = {**os.environ, "MCP_TIMEOUT": "30000"}

    try:
        proc = subprocess.run(args, capture_output=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=_TURN_TIMEOUT_SECONDS, env=env, cwd=_neutral_cwd())
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"claude did not respond within {_TURN_TIMEOUT_SECONDS}s"}
    except OSError as e:
        return {"ok": False, "error": f"Failed to launch claude: {e}"}

    if proc.returncode != 0:
        logger.warning("claude exited %s: %s", proc.returncode, proc.stderr)
        return {"ok": False, "error": (proc.stderr or proc.stdout or f"claude exited {proc.returncode}").strip()[:2000]}

    text, returned_session_id = _parse_claude_output(proc.stdout)
    return {"ok": True, "response": text, "session_id": returned_session_id or resolved_session_id}


def _parse_claude_output(stdout: str) -> tuple[str, Optional[str]]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip(), None
    text = payload.get("result") or payload.get("response") or ""
    return text, payload.get("session_id")


def _run_codex_turn(message: str, session_id: Optional[str]) -> Dict[str, Any]:
    codex_path = shutil.which("codex")
    if codex_path is None:
        return {"ok": False, "error": "'codex' CLI not found on PATH. Install Codex CLI and sign in first."}

    _ensure_codex_mcp_registered(codex_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = os.path.join(tmp_dir, "last_message.txt")
        base = [codex_path, "exec"]
        if session_id:
            base += ["resume", session_id]
        # message is untrusted user input and must not be parsed as a flag if
        # it starts with "-" — "--" tells codex's CLI parser everything after
        # it is positional, so flags all go before it, message last.
        base += ["--sandbox", "read-only", "--skip-git-repo-check", "--json", "-o", out_path, "--", message]

        try:
            proc = subprocess.run(base, capture_output=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=_TURN_TIMEOUT_SECONDS, cwd=_neutral_cwd())
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"codex did not respond within {_TURN_TIMEOUT_SECONDS}s"}
        except OSError as e:
            return {"ok": False, "error": f"Failed to launch codex: {e}"}

        if proc.returncode != 0:
            logger.warning("codex exited %s: %s", proc.returncode, proc.stderr)
            return {"ok": False, "error": (proc.stderr or proc.stdout or f"codex exited {proc.returncode}").strip()[:2000]}

        returned_session_id = _parse_codex_session_id(proc.stdout) or session_id
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
        except OSError:
            text = proc.stdout.strip()

    return {"ok": True, "response": text, "session_id": returned_session_id}


def _parse_codex_session_id(stdout: str) -> Optional[str]:
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("session_id", "conversation_id", "thread_id"):
            value = event.get(key)
            if value:
                return value
    return None


def _ensure_codex_mcp_registered(codex_path: str) -> None:
    """Registers this hub as a Codex MCP server once. Codex has no per-call
    equivalent of Claude's --mcp-config; `codex mcp add` is the CLI's own
    persistent-config mechanism, so this uses it rather than hand-editing
    ~/.codex/config.toml."""
    global _CODEX_REGISTRATION_CHECKED
    if _CODEX_REGISTRATION_CHECKED:
        return
    _CODEX_REGISTRATION_CHECKED = True

    try:
        listed = subprocess.run([codex_path, "mcp", "list"], capture_output=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=15)
        if _MCP_SERVER_NAME in (listed.stdout or ""):
            return
        subprocess.run(
            [codex_path, "mcp", "add", _MCP_SERVER_NAME, "--", *_mcp_server_command()],
            capture_output=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=15,
        )
        logger.info("Registered '%s' as a Codex MCP server", _MCP_SERVER_NAME)
    except Exception:
        logger.warning("Could not verify/register the Codex MCP server", exc_info=True)
