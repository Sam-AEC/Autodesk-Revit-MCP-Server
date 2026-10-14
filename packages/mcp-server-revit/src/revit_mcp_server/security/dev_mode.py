"""Explicit panel-controlled Dev mode, shared by processes using one workspace.

Unlike timed Auto, this signed override has no expiry or document binding. Only
the authenticated panel route writes it; there is no model-facing toggle tool.
It changes approval only, never filesystem scope, read-mode guards or redaction.
The panel token authenticates a local process, not a person's physical presence.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import redact_data
from .approval_override import disable_auto, enable_auto
from .panel_token import PanelTokenError, _restrict_windows_acl, is_valid_token, read_token, token_path

DEV_FILENAME = ".dev-mode.json"
AUDIT_FILENAME = "dev-mode-audit.jsonl"
_AUDIT_LOCK = threading.RLock()


def dev_path(workspace_dir: Path) -> Path:
    return Path(workspace_dir) / DEV_FILENAME


def _workspace_key(workspace_dir: Path) -> str:
    workspace = os.path.normcase(str(Path(workspace_dir).resolve()))
    return hashlib.sha256(workspace.encode("utf-8")).hexdigest()


def _authority_path(workspace_dir: Path) -> Path:
    """Trusted nonce next to the owner-only token, outside model file tools' scope."""
    key_path = token_path()
    return key_path.with_name(key_path.name + ".dev") / (_workspace_key(workspace_dir) + ".json")


def _sign(token: str, workspace_dir: Path, set_at: int, nonce: str) -> str:
    workspace = os.path.normcase(str(Path(workspace_dir).resolve()))
    message = json.dumps(["dev", workspace, set_at, nonce], separators=(",", ":")).encode("utf-8")
    return hmac.new(token.encode("ascii"), message, hashlib.sha256).hexdigest()


def _write_record(path: Path, record: dict[str, Any], *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temporary files avoid collisions between concurrent panel requests.
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if private and os.name == "nt":
                _restrict_windows_acl(Path(name))
            json.dump(record, fh)
        # The existing Windows-aware replace helper retries only file contention.
        from .approval import replace_with_retry
        replace_with_retry(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def enable_dev(workspace_dir: Path, *, token: str, now: float | None = None) -> None:
    if not is_valid_token(token):
        raise PanelTokenError("A valid panel token is required to enable Dev mode.")
    set_at = int(time.time() if now is None else now)
    nonce = secrets.token_hex(32)
    record = {"mode": "dev", "set_at": set_at, "nonce": nonce,
              "sig": _sign(token, workspace_dir, set_at, nonce)}
    # Updating trusted authority first invalidates every previous workspace
    # record, including copies an agent might restore after Off or re-enable.
    _write_record(_authority_path(workspace_dir), record, private=True)
    _write_record(dev_path(workspace_dir), record)


def disable_dev(workspace_dir: Path) -> None:
    # Revocation precedes workspace cleanup: a failed unlink cannot reactivate
    # an old signed record. No workspace-controlled generation is authoritative.
    _authority_path(workspace_dir).unlink(missing_ok=True)
    dev_path(workspace_dir).unlink(missing_ok=True)


def active_dev(workspace_dir: Path, *, token: str | None = None) -> bool:
    """Fail closed on missing, malformed, copied or unsigned overrides."""
    try:
        record = json.loads(dev_path(workspace_dir).read_text(encoding="utf-8"))
        if not isinstance(record, dict) or set(record) != {"mode", "set_at", "nonce", "sig"}:
            return False
        set_at, sig, nonce = record["set_at"], record["sig"], record["nonce"]
        if record["mode"] != "dev" or type(set_at) is not int or set_at < 0 or not isinstance(sig, str):
            return False
        if not isinstance(nonce, str) or len(nonce) != 64 or any(c not in "0123456789abcdef" for c in nonce):
            return False
        key = token if token is not None else read_token()
        if not key or not is_valid_token(key) or not hmac.compare_digest(sig, _sign(key, workspace_dir, set_at, nonce)):
            return False
        authority = json.loads(_authority_path(workspace_dir).read_text(encoding="utf-8"))
        return isinstance(authority, dict) and authority == record
    except (OSError, ValueError, UnicodeError, PanelTokenError):
        return False


def audit_dev_event(workspace_dir: Path, event: str, **fields: Any) -> None:
    """Persist a redacted event before allowing the operation; errors propagate.

    Sharing the gate's file-lock helper keeps parallel processes' JSON lines
    complete. Import lazily because ApprovalGate reads this module's state.
    """
    from .approval import _locked_file
    path = Path(workspace_dir) / AUDIT_FILENAME
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with _AUDIT_LOCK, _locked_file(path.with_suffix(".lock")):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(redact_data(entry), default=str) + "\n")


def set_panel_mode(workspace_dir: Path, mode: str, *, token: str, minutes: Any = None) -> None:
    """Serialize person-requested mode switches across threads and hub processes.

    Called only after the panel route checks auth, configured look_only and
    explicit confirmation. Audit records intent before changing the state.
    """
    from .approval import _locked_file
    if mode not in {"dev", "auto", "ask_first", "required"}:
        raise ValueError("Unknown panel approval mode")
    with _AUDIT_LOCK, _locked_file(_authority_path(workspace_dir).with_suffix(".lock")):
        if mode == "dev" or active_dev(workspace_dir, token=token):
            audit_dev_event(workspace_dir, "toggle_requested", mode=mode, source="panel")
        if mode == "dev":
            enable_dev(workspace_dir, token=token)
            disable_auto(workspace_dir)
        elif mode == "auto":
            enable_auto(workspace_dir, minutes, token=token)
            disable_dev(workspace_dir)
        else:
            disable_dev(workspace_dir)
            disable_auto(workspace_dir)
