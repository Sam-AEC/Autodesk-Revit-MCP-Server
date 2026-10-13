"""Live, time-limited switch to ``auto`` approval mode, set from the panel.

``MCP_REVIT_APPROVAL_MODE`` is read once when a process starts, so it cannot be
flipped while Revit and the agent are running. This module adds the one thing the
panel needs: a short "auto for the next N minutes" window that every gate (the
agent's MCP server, the panel hub, the CLI) picks up on its next call.

How it stays safe:

* The record lives in the workspace (``.approval-mode.json``) so every process that
  shares the plans folder sees it, but the workspace is a place the agent's file
  tools can write to. So the record is signed with HMAC-SHA256 keyed by the panel
  hub token (``%LOCALAPPDATA%\\AECModelBridge\\panel-hub.token``), which lives
  outside the workspace sandbox. A record without a valid signature is ignored.
* Only the hub writes it, behind the same token check as every other hub route.
  No MCP tool can set it.
* It only ever turns ``auto`` ON, and always with an expiry (default 30 minutes,
  at most 8 hours). Expired, unsigned, malformed or unreadable means "ignore it":
  the gate falls back to the mode the process started with.
* It never relaxes ``look_only``: that is an explicit lockdown set in the
  environment, and a click in the panel must not undo it.

Like the token itself this proves "a local process running as this user", not that
a person is present (see docs/security.md).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .panel_token import PanelTokenError, read_token

logger = logging.getLogger(__name__)

OVERRIDE_FILENAME = ".approval-mode.json"
DEFAULT_AUTO_MINUTES = 30
MAX_AUTO_MINUTES = 8 * 60
MIN_AUTO_MINUTES = 1

_warned_bad_signature = False


def override_path(workspace_dir: Path) -> Path:
    return Path(workspace_dir) / OVERRIDE_FILENAME


def _sign(token: str, set_at: int, expires_at: int) -> str:
    message = f"auto|{set_at}|{expires_at}".encode("ascii")
    return hmac.new(token.encode("ascii"), message, hashlib.sha256).hexdigest()


def clamp_minutes(minutes: Any) -> int:
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        value = DEFAULT_AUTO_MINUTES
    return max(MIN_AUTO_MINUTES, min(MAX_AUTO_MINUTES, value))


def enable_auto(workspace_dir: Path, minutes: Any = DEFAULT_AUTO_MINUTES, *, token: str, now: Optional[float] = None) -> Dict[str, Any]:
    """Write a signed 'auto until <time>' record. Returns {"expires_at", "minutes"}."""
    now_s = int(time.time() if now is None else now)
    span = clamp_minutes(minutes)
    expires_at = now_s + span * 60
    record = {"mode": "auto", "set_at": now_s, "expires_at": expires_at, "sig": _sign(token, now_s, expires_at)}
    path = override_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, path)
    return {"expires_at": expires_at, "minutes": span}


def disable_auto(workspace_dir: Path) -> None:
    try:
        override_path(workspace_dir).unlink()
    except FileNotFoundError:
        pass


def active_override(workspace_dir: Path, *, token: Optional[str] = None, now: Optional[float] = None) -> Optional[Dict[str, int]]:
    """Return {"set_at", "expires_at"} while a valid, unexpired, correctly signed 'auto' record exists.

    Anything else (no file, bad JSON, wrong signature, expired, expiry too far out, no token
    file to verify with) returns None. Never raises.
    """
    path = override_path(workspace_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        record = json.loads(raw)
        if not isinstance(record, dict) or record.get("mode") != "auto":
            return None
        set_at = record["set_at"]
        expires_at = record["expires_at"]
        sig = record["sig"]
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (set_at, expires_at)) or not isinstance(sig, str):
            return None
    except (ValueError, KeyError):
        return None

    now_s = time.time() if now is None else now
    if expires_at <= now_s or expires_at - set_at > MAX_AUTO_MINUTES * 60 or set_at > now_s + 300:
        return None

    try:
        key = token if token is not None else read_token()
    except PanelTokenError:
        return None
    if not key:
        return None
    if not hmac.compare_digest(sig, _sign(key, set_at, expires_at)):
        global _warned_bad_signature
        if not _warned_bad_signature:
            _warned_bad_signature = True
            logger.warning("Ignoring %s: its signature does not match the panel token.", OVERRIDE_FILENAME)
        return None
    return {"set_at": set_at, "expires_at": expires_at}
