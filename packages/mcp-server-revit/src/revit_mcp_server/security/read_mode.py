"""Read mode for `revit_execute_python`: a safety rail, not a security boundary.

`mode="read"` promises that a script only inspects the model. The MCP side then
skips the approval gate for that call, so the check here must run before the
gate is skipped and must fail closed. The add-in repeats the same check and adds
a runtime backstop (`PythonScriptRunner.cs`); keep the two token lists in step
(tests/test_python_read_mode.py compares them).

The name check is only a first filter. The add-in also runs every read-mode script inside a transaction group that it
always rolls back, so a script that gets past the names (seen live: getattr(DB, 'Trans' + 'action')) leaves no change in
the model and is reported as a read_mode_violation.

What the name check catches: any mention of Transaction, SubTransaction or TransactionGroup
(including `from Autodesk.Revit.DB import Transaction`), the calls that save or
synchronise a document, and dynamic-code builtins that could assemble those
names at run time. What it cannot catch: reflection or string tricks that reach
the API without the literal names. Treat write-capable scripts as write mode.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

MODE_READ = "read"
MODE_WRITE = "write"
VALID_MODES = (MODE_READ, MODE_WRITE)

# (rule name, pattern). Whole-word, case-sensitive, matched against the raw script text.
FORBIDDEN_IN_READ_MODE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Transaction", re.compile(r"\bTransaction\b")),
    ("SubTransaction", re.compile(r"\bSubTransaction\b")),
    ("TransactionGroup", re.compile(r"\bTransactionGroup\b")),
    ("Save", re.compile(r"\.\s*Save(?:As)?\s*\(")),
    ("SynchronizeWithCentral", re.compile(r"\bSynchronizeWithCentral\b")),
    ("PostCommand", re.compile(r"\bPostCommand\b")),
    ("eval", re.compile(r"\beval\b")),
    ("exec", re.compile(r"\bexec(?:file)?\b")),
    ("__import__", re.compile(r"\b__import__\b")),
    # A read-mode script runs without approval, so it must not reach the file system, processes or the network.
    ("os_modules", re.compile(r"\b(?:import|from)\s+(?:os|subprocess|shutil|socket|ctypes|urllib\w*|http|ftplib|smtplib|pickle|marshal|webbrowser|tempfile|glob|io)\b")),
    ("System.IO", re.compile(r"\bSystem\s*\.\s*(?:IO|Net|Reflection)\b|\bProcess(?:StartInfo)?\s*[.(]")),
    ("open", re.compile(r"(?<![\w.])(?:open|file)\s*\(")),
)


class ReadModeViolation(ValueError):
    """A script marked mode='read' contains something that could change the model."""


def normalize_mode(value: Any) -> str:
    """Return 'read' or 'write'; a missing value means write. Anything else is an error."""
    if value is None:
        return MODE_WRITE
    if isinstance(value, str) and value.strip().lower() in VALID_MODES:
        return value.strip().lower()
    raise ValueError(f"mode must be 'read' or 'write', got {value!r}")


def find_violations(script: str) -> list[str]:
    return [name for name, pattern in FORBIDDEN_IN_READ_MODE if pattern.search(script)]


def validate_read_script(script: Any) -> None:
    if not isinstance(script, str) or not script.strip():
        raise ReadModeViolation("read mode needs a non-empty script string")
    hits = find_violations(script)
    if hits:
        raise ReadModeViolation(
            "Read mode refuses scripts that could change the model (found: "
            + ", ".join(hits)
            + "). Use mode='write' with an approved plan_id for scripts that open transactions."
        )


def is_read_mode_call(arguments: Mapping[str, Any] | None) -> bool:
    """True only for a valid read-mode script. Raises for a read-mode script that breaks the rules.

    Callers use this to decide whether the approval gate applies, so every
    unexpected shape must come back as False (gated), never as True.
    """
    if not isinstance(arguments, Mapping):
        return False
    try:
        mode = normalize_mode(arguments.get("mode"))
    except ValueError:
        return False
    if mode != MODE_READ:
        return False
    validate_read_script(arguments.get("script"))
    return True


def execute_python_payload(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Bridge payload for revit.execute_python; enforces the read-mode rules before anything is sent."""
    mode = normalize_mode(arguments.get("mode"))
    script = arguments.get("script")
    if mode == MODE_READ:
        validate_read_script(script)
    return {"script": script, "mode": mode}
