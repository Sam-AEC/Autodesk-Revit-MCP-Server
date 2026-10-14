"""
revit_params module - read and batch-set instance or type parameters of placed elements from data.

Commands (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  get_parameters   read-only  values of named (or all) parameters of selected elements, with the unit the write tool
                              expects and whether it would write them; capped rows, truncated flag, time budget
  set_parameters   WRITE      set parameters of up to 500 elements from data, old -> new per value, read back afterwards

Selecting elements (both tools, per item): ``id``, ``ids`` or ``selector`` {category, name, level, tag}. A selector needs a
category or a tag (Comments prefix) so the whole model is never scanned unasked; name (element name) and level (level
name) narrow it. ``scope`` 'instance' (default) means the selected element itself, 'type' its element type (two
instances of one type write that type once).

Units are explicit (see scripts/_params.ipy): mm, m (lengths), deg (angles), number (other Double parameters, internal
units), int, bool (Yes/No), text, elementid (an element given by name or integer id). A plain JSON true/false means bool,
a plain string means text, a plain whole number means int; a Double parameter always needs a unit.

How it works: the same seam as ``revit_docs`` (read its module.py header). Each command builds an IronPython 2.7 script
from the revit module's ``_prelude.ipy`` (+ for the write command the revit_docs ``_tags_read.ipy`` and
``_write_prelude.ipy``: Runner, Collector, dry run; reused by path, not copied), this module's ``_params.ipy`` and the
command script, injects the arguments as an ``ARGS`` literal and runs it in Revit; the printed line protocol becomes the
plan section 6 contract (``revit_mcp_server.check_contract``).

Safety of the write command:
  * ``is_mutating`` in module.json: the approval gate demands an approved plan_id first (also for ``dry_run``);
  * every element and value is checked before anything changes. It never creates a parameter; a missing, ambiguous,
    read-only or built-in critical parameter (type / family / category, workset / phase / design option, IFC GUID,
    level and host constraints), a unit that does not fit, or an element name that matches zero or several elements is
    refused with a reason per element. on_error 'abort' (default) refuses the whole call before any change; 'skip'
    leaves the refused elements alone and writes the rest;
  * one TransactionGroup per call, one Transaction per element; a failure rolls back that element (skip) or the whole
    call (abort); Revit warnings are dismissed and listed;
  * every written value is read back inside the group (post-check). Each row says old -> new -> read back, and the result
    carries ``revert``: items in this tool's own input format that put the old values back;
  * ``dry_run``: the whole call runs inside the group as normal, then the group is always rolled back.

UNVERIFIED: nothing here has run against a live Revit. The scripts are syntax-checked and exercised against a stub of the
Revit API with an undo journal (tests/revit_mep_stub.py, tests/test_revit_params*.py). Specifically unproven in a live
model: Element.GetParameters(name), Definition.GetDataType() / SpecTypeId comparisons (and the older ParameterType
fallback), the built-in ids of the refused parameters, Parameter.Set return values, ElementId lookups by name with
OfClass(type(element)), and Element.LevelId for the level selector.
"""
from __future__ import annotations

import math
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from revit_mcp_server.check_contract import (
    DRY_RUN_HINT,
    PageSpec,
    ScriptOutput,
    assemble_result,
    error_result,
    mock_result,
    parse_script_output,
    write_run_fields,
)

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
REVIT_PRELUDE = MODULE_DIR.parent / "revit" / "scripts" / "_prelude.ipy"
DOCS_SCRIPT_DIR = MODULE_DIR.parent / "revit_docs" / "scripts"
TAGS_READ = DOCS_SCRIPT_DIR / "_tags_read.ipy"
WRITE_PRELUDE = DOCS_SCRIPT_DIR / "_write_prelude.ipy"
HELPERS = "_params.ipy"
EXECUTE_TOOL = "revit_execute_python"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

# script name -> write script?
SCRIPTS: Dict[str, bool] = {"set_parameters.ipy": True, "get_parameters.ipy": False}

MAX_WRITE_ELEMENTS = 500
MAX_PARAMS_PER_ITEM = 50
UNITS = ("mm", "m", "deg", "number", "int", "bool", "text", "elementid")
NUMBER_UNITS = ("mm", "m", "deg", "number")
_TAG = re.compile(r"^[ -~]{1,80}$")  # printable ASCII only

_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "element_not_found": "Check the element ids (revit_get_parameters or a selector finds them). Nothing was changed.",
    "empty_selection": "The selector matched nothing. Check category, name, level and tag with revit_get_parameters. Nothing was changed.",
    "too_many_elements": "At most 500 elements per call. Narrow the selectors or split the call. Nothing was changed.",
    "too_many_values": "Split the call into smaller batches. Nothing was changed.",
    "conflicting_values": "The same element got two different values for one parameter (two items, or two instances of one type with scope 'type'). Nothing was changed.",
    "parameter_refused": "Nothing was changed. Read the reason per element in rows (status refused): use revit_get_parameters to see the parameter names, units and which ones are writable, fix the items, or pass on_error='skip' to write the others.",
    "rolled_back": "Nothing was changed: the whole call was rolled back. Fix the cause named in fails and call again, or pass on_error='skip' to keep what worked.",
    "partial_failure": "The elements that worked were written (see changed_ids and rows with status set); refused or failed ones are in fails and rows. Use revert to undo the written values.",
    "post_check_failed": "A value did not read back as written (see post_check). Inspect the element with revit_get_parameters; use revert to put the old values back.",
    "script_exception": "The embedded script failed inside Revit; any open transaction group was rolled back, so the model should be unchanged (verify with revit_get_parameters).",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id, and do not repeat a write until it has finished.",
    "dry_run_not_honoured": "A dry run reported committed changes. Check the elements with revit_get_parameters before doing anything else.",
}


# --------------------------------------------------------------------------- #
# Script building and the seams to Revit (same shape as revit_docs)
# --------------------------------------------------------------------------- #
def py2_literal(value: Any) -> str:
    """Python 2.7 source for a JSON-like value; strings become ``u'...'`` with ``\\uXXXX`` escapes (IronPython 2.7 needs the u)."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("numbers must be finite")
        return repr(value)
    if isinstance(value, str):
        out: List[str] = []
        for ch in value:
            code = ord(ch)
            if ch == "\\":
                out.append("\\\\")
            elif ch == "'":
                out.append("\\'")
            elif 0x20 <= code < 0x7F:
                out.append(ch)
            elif code > 0xFFFF:
                code -= 0x10000
                out.append("\\u%04x\\u%04x" % (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
            else:
                out.append("\\u%04x" % code)
        return "u'" + "".join(out) + "'"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(py2_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{py2_literal(str(k))}: {py2_literal(v)}" for k, v in value.items()) + "}"
    raise ValueError(f"cannot embed a {type(value).__name__} in a script")


def build_script(script_name: str, args: Dict[str, Any]) -> str:
    """Prelude(s) + helpers + ``ARGS`` literal + the command script. The read script gets no write prelude."""
    write = SCRIPTS[script_name]
    parts = [REVIT_PRELUDE.read_text(encoding="utf-8")]
    if write:
        parts.append(TAGS_READ.read_text(encoding="utf-8"))
        parts.append(WRITE_PRELUDE.read_text(encoding="utf-8"))
    parts.append((SCRIPT_DIR / HELPERS).read_text(encoding="utf-8"))
    parts.append(f"ARGS = {py2_literal(args)}")
    parts.append((SCRIPT_DIR / script_name).read_text(encoding="utf-8"))
    return "\n\n".join(parts) + "\n"


def run_read_script(script: str, tool_executor: ToolExecutor) -> Any:
    """Send a read-only script to Revit (mode 'read': no approval, cannot open a transaction)."""
    return tool_executor(EXECUTE_TOOL, {"script": script, "mode": "read"})


def run_write_script(script: str, approved_executor: ToolExecutor) -> Any:
    """Send a write script to Revit. Only the write command calls this, with the executor the approval gate handed it."""
    return approved_executor(EXECUTE_TOOL, {"script": script, "mode": "write"})


def _server_in_mock_mode() -> bool:
    try:
        from revit_mcp_server.config import BridgeMode, config

        return config.mode == BridgeMode.mock
    except Exception:  # noqa: BLE001 - a config problem must not hide a real bridge
        return False


def _is_mock(raw: Any) -> bool:
    if isinstance(raw, dict):
        if raw.get("mock"):
            return True
        data = raw.get("data")
        return isinstance(data, dict) and bool(data.get("mock"))
    return False


def _is_running(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("status") == "running" and bool(raw.get("request_id"))


def _script_text(raw: Any) -> Tuple[Optional[str], str]:
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict) and "output" not in raw:
        raw = raw["data"]
    if not isinstance(raw, dict):
        return None, f"unexpected answer from the bridge: {type(raw).__name__}"
    if raw.get("success") is False:
        return None, str(raw.get("error") or "the script failed without a message")
    if "output" not in raw:
        return None, "the bridge answer has no 'output' field"
    return str(raw.get("output") or ""), str(raw.get("error") or "")


def _bridge_failure(tool: str, exc: Exception) -> Dict[str, Any]:
    text = str(exc)
    low = text.lower()
    if "approval" in low or "plan_id" in low:
        return error_result(tool, "approval_required", text, hint="The approval gate refused the call. Nothing was sent to Revit.")
    if "timed out" in low or "timeout" in low:
        return error_result(tool, "timeout_running", text, hint=_HINTS["timeout_running"])
    return error_result(tool, "bridge_error", text, hint="Check that Revit is running with the AEC Model Bridge add-in and a project open (revit_health).")


def _ints(text: Optional[str]) -> List[int]:
    return [int(p) for p in (text or "").split(",") if p.strip().lstrip("-").isdigit()]


def _mock(tool: str, write: bool) -> Dict[str, Any]:
    result = mock_result(tool)
    if write:
        result["post_check"] = {"ok": None, "checked": 0, "failed": 0, "checks": []}
    return result


def _running(tool: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Revit is still busy with the script; nothing was lost and the outcome is not known yet."""
    return {
        "tool": tool,
        "status": "running",
        "request_id": raw.get("request_id"),
        "verified": False,
        "summary": "Revit is still working on this request; the outcome is not known yet.",
        "message": raw.get("message") or "Call revit_get_result with this request_id to collect the output.",
        "hint": _HINTS["timeout_running"],
        "changed_ids": [],
        "post_check": None,
    }


def _run(
    tool: str,
    script_name: str,
    script_args: Dict[str, Any],
    *,
    write: bool,
    tool_executor: Optional[ToolExecutor],
    approved_executor: Optional[ToolExecutor],
) -> Tuple[Optional[ScriptOutput], int, Optional[Dict[str, Any]]]:
    """Run one script. Returns ``(parsed, elapsed_ms, early_result)``; ``early_result`` is an error, mock or running contract."""
    if _server_in_mock_mode():
        return None, 0, _mock(tool, write)
    executor = approved_executor if write else tool_executor
    if executor is None:
        return None, 0, error_result(
            tool,
            "no_bridge",
            "No connection to the Revit tools in this session." if not write else "No approved connection to Revit: a write command must run through the approval gate.",
            hint="This tool must run inside the AEC Model Bridge server (module provider with a tool registry).",
        )
    script = build_script(script_name, script_args)
    started = time.perf_counter()
    try:
        raw = run_write_script(script, executor) if write else run_read_script(script, executor)
    except Exception as exc:  # noqa: BLE001 - classified into a structured error
        return None, 0, _bridge_failure(tool, exc)
    elapsed = int((time.perf_counter() - started) * 1000)
    if _is_mock(raw):
        return None, elapsed, _mock(tool, write)
    if _is_running(raw):
        return None, elapsed, _running(tool, raw)
    text, err = _script_text(raw)
    if text is None:
        return None, elapsed, error_result(tool, "script_error", err, hint="The add-in reported a script error before any result was produced." + (" Check the model before repeating a write." if write else " Read-only: the model is unchanged."))
    parsed = parse_script_output(text)
    if parsed.errors:
        kind, message = parsed.errors[0]
        result = error_result(tool, kind, message, hint=_HINTS.get(kind, ""))
        if write:
            result["changed_ids"] = _ints(parsed.meta.get("changed_ids"))
            result["outcome"] = parsed.meta.get("outcome")
            result["post_check"] = None
        return None, elapsed, result
    if not parsed.summary and not parsed.counts:
        return None, elapsed, error_result(tool, "unparsable_output", "The script printed no summary and no counts (ignored %d lines)." % parsed.ignored_lines, hint="The add-in may run an older or different IronPython engine; call revit_get_context and report the build.")
    return parsed, elapsed, None


# --------------------------------------------------------------------------- #
# Argument helpers
# --------------------------------------------------------------------------- #
def _text(value: Any, what: str, limit: int = 200) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(f"{what} is required")
    if len(text) > limit:
        raise ValueError(f"{what} is longer than {limit} characters")
    if any(ord(c) < 32 for c in text):
        raise ValueError(f"{what} contains control characters")
    return text


def _int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{what} must be an integer")
    return int(value)


def _num(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{what} must be a finite number")
    return float(value)


def _flag(value: Any, what: str) -> bool:
    """A strict boolean (None means false): the string 'false' must never turn into a real write or a dry run."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(f"{what} must be true or false")
    return value


def _choice(value: Any, allowed: Tuple[str, ...], what: str, default: Optional[str] = None) -> str:
    if value in (None, ""):
        if default is None:
            raise ValueError(f"{what} is required: one of {', '.join(allowed)}")
        return default
    if value not in allowed:
        raise ValueError(f"{what} must be one of {', '.join(allowed)}, got {value!r}")
    return str(value)


def _bounded(value: Any, what: str, default: float, low: float, high: float) -> float:
    number = default if value is None else _num(value, what)
    if not low <= number <= high:
        raise ValueError(f"{what} must be between {low:g} and {high:g}")
    return number


def _bad_input(tool: str, exc: Exception) -> Dict[str, Any]:
    return error_result(tool, "invalid_input", str(exc), hint=_HINTS["invalid_input"])


def _selection(item: Any, what: str, max_ids: int) -> Tuple[Dict[str, Any], int]:
    """The element part of an item: ({"ids": [...]} or {"selector": {...}}, number of ids), plus its scope."""
    if not isinstance(item, dict):
        raise ValueError(f"{what} must be an object")
    given = [k for k in ("id", "ids", "selector") if item.get(k) not in (None, "", [], {})]
    if len(given) != 1:
        raise ValueError(f"{what} needs exactly one of id, ids or selector")
    out: Dict[str, Any] = {"scope": _choice(item.get("scope"), ("instance", "type"), f"{what}.scope", "instance")}
    if given[0] == "id":
        out["ids"] = [_int(item["id"], f"{what}.id")]
    elif given[0] == "ids":
        ids = item["ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= max_ids:
            raise ValueError(f"{what}.ids must be a list of 1 to {max_ids} element ids")
        out["ids"] = [_int(i, f"{what}.ids") for i in ids]
    else:
        sel = item["selector"]
        if not isinstance(sel, dict) or set(sel) - {"category", "name", "level", "tag"}:
            raise ValueError(f"{what}.selector must be an object with category, name, level and/or tag")
        clean = {k: _text(sel[k], f"{what}.selector.{k}") for k in ("category", "name", "level", "tag") if sel.get(k) not in (None, "")}
        if not clean.get("category") and not clean.get("tag"):
            raise ValueError(f"{what}.selector needs a category or a tag, so the whole model is never scanned")
        if clean.get("tag") and not _TAG.match(clean["tag"]):
            raise ValueError(f"{what}.selector.tag must be 1-80 printable ASCII characters")
        out["selector"] = clean
    return out, len(out.get("ids", []))


def _value(name: str, raw: Any, what: str) -> Dict[str, Any]:
    """{value, unit} from a plain value or an object; the unit is checked against the value here, against the parameter in Revit."""
    unit = ""
    value = raw
    if isinstance(raw, dict):
        if set(raw) - {"value", "unit"} or "value" not in raw:
            raise ValueError(f"{what}['{name}'] must be a value or an object with value and unit")
        value = raw["value"]
        unit = _choice(raw.get("unit"), UNITS, f"{what}['{name}'].unit", "")
    if value is None or isinstance(value, (list, dict)):
        raise ValueError(f"{what}['{name}'] must be a number, true/false or text")
    where = f"{what}['{name}']"
    if unit in NUMBER_UNITS:
        value = _num(value, where)
    elif unit == "int":
        value = _int(value, where)
    elif unit == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{where} with unit bool must be true or false")
    elif unit == "text":
        if not isinstance(value, str):
            raise ValueError(f"{where} with unit text must be text")
    elif unit == "elementid":
        if isinstance(value, bool) or not (isinstance(value, str) and value.strip()) and not (isinstance(value, int) and value > 0):
            raise ValueError(f"{where} with unit elementid must be an element name or a positive integer id")
    else:  # no unit: true/false means bool, text means text, a whole number means int; a Double always needs a unit
        if isinstance(value, bool):
            unit = "bool"
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(f"{where} must be finite")
            if value != int(value):
                raise ValueError(f"{where} is a fraction: give a unit (mm, m, deg or number)")
            value = int(value)
    if isinstance(value, str) and len(value) > 4000:
        raise ValueError(f"{where} is longer than 4000 characters")
    return {"value": value, "unit": unit}


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #
ITEM_TYPES = {"id": "int", "element_id": "int"}
READ_TYPES = {"id": "int", "element_id": "int", "value_id": "int", "read_only": "bool", "writable": "bool"}


def _typed_old(row: Dict[str, Any]) -> Any:
    unit, storage, old = row.get("unit", ""), row.get("storage", ""), row.get("old_raw", "")
    if storage == "ElementId":
        return int(old) if str(old).lstrip("-").isdigit() and int(old) > 0 else None
    if storage == "String":
        return old
    if old in ("", None):
        return None
    if unit == "bool":
        return str(old) not in ("0", "", "False")
    if storage == "Integer":
        return int(old)
    number = float(old)
    return {"mm": number * 304.8, "m": number * 0.3048, "deg": number * 180.0 / math.pi}.get(unit, number)


def revert_items(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """revit_set_parameters items that put back the old values of every row with status set (by target id, scope instance)."""
    by_id: Dict[int, Dict[str, Any]] = {}
    skipped: List[str] = []
    for r in rows:
        if r.get("status") != "set":
            continue
        try:
            target = int(r["id"])
            old = _typed_old(r)
        except (KeyError, TypeError, ValueError):
            skipped.append(str(r.get("param")))
            continue
        if old is None:
            skipped.append(f"{r.get('id')}:{r.get('param')} (had no value)")
            continue
        unit = "elementid" if r.get("storage") == "ElementId" else (r.get("unit") or "")
        entry = by_id.setdefault(target, {"id": target, "scope": "instance", "params": {}})
        entry["params"][str(r.get("param"))] = {"value": old, "unit": unit} if unit else old
    return list(by_id.values()), skipped


def _finish_write(
    tool: str,
    parsed: ScriptOutput,
    elapsed: int,
    workspace: Any,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    outcome = parsed.meta.get("outcome", "ok")
    changed = _ints(parsed.meta.get("changed_ids"))
    failed_ids = _ints(parsed.meta.get("failed_ids"))
    posts = [r for r in parsed.rows if r.get("row_type") == "post"]
    items = [{k: v for k, v in r.items() if k != "row_type"} for r in parsed.rows if r.get("row_type") == "item"]
    checks = [{"check": r.get("check"), "ok": r.get("ok") == "1", "detail": r.get("detail", "")} for r in posts]
    checks.sort(key=lambda c: c["ok"])  # failures first
    failed_checks = sum(1 for c in checks if not c["ok"])
    post_check = {"ok": failed_checks == 0, "checked": len(checks), "failed": failed_checks, "checks": checks[:40]}
    if outcome == "ok" and not post_check["ok"]:
        outcome = "post_check_failed"

    synthetic = ScriptOutput(
        summary=parsed.summary,
        fails=list(parsed.fails),
        infos=list(parsed.infos),
        rows=items,
        meta=dict(parsed.meta),
        counts={"fail": parsed.counts.get("fail", len(parsed.fails)), "info": parsed.counts.get("info", len(parsed.infos)), "row": len(items)},
    )
    statuses: Dict[str, int] = {}
    for it in items:
        statuses[str(it.get("status"))] = statuses.get(str(it.get("status")), 0) + 1
    revert, not_revertable = revert_items(items) if not dry_run and outcome in ("ok", "partial_failure", "post_check_failed") else ([], [])
    fields: Dict[str, Any] = {
        "changed_ids": changed if outcome in ("ok", "partial_failure", "post_check_failed") else [],
        "post_check": post_check,
        "outcome": outcome,
        "on_error": parsed.meta.get("on_error"),
        "warnings_dismissed": int(parsed.meta.get("warnings_dismissed", "0") or 0),
        "values": statuses,
        "revert": {"items": revert, "not_revertable": not_revertable,
                   "how": "Call revit_set_parameters with these items (under a new approved plan) to put the old values back."},
    }
    run_fields, violation = write_run_fields(parsed, outcome, items, dry_run=dry_run)
    fields.update(run_fields)
    if violation:
        synthetic.fails.insert(0, violation)
        outcome = "dry_run_not_honoured"
        fields["outcome"] = outcome
    ok = outcome == "ok" and post_check["ok"] and not synthetic.fails and parsed.counts.get("fail", 0) == 0
    summary = parsed.summary
    if not ok:
        first = synthetic.fails[0] if synthetic.fails else outcome
        summary = f"FAILED ({outcome}): {first}"
        if outcome in ("rolled_back", "parameter_refused"):
            summary += " Nothing was changed."
    if dry_run:
        summary = "DRY RUN, nothing was changed: " + (summary or "")
    result = assemble_result(
        tool,
        synthetic,
        PageSpec(limit=500),
        row_types=ITEM_TYPES,
        elapsed_ms=elapsed,
        workspace=workspace,
        summary=summary,
        extra=fields,
    )
    if not ok:
        result["ok"] = False
        result["kind"] = outcome if outcome != "ok" else "post_check_failed"
        result["message"] = synthetic.fails[0] if synthetic.fails else f"outcome: {outcome}"
        result["element_ids"] = failed_ids
        result["hint"] = _HINTS.get(result["kind"], "")
    if dry_run and not violation:
        result["hint"] = (DRY_RUN_HINT + " " + result.get("hint", "")).strip()
    return result


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
class RevitParamsModule:

    # ---- read-only ---------------------------------------------------------- #
    def get_parameters(
        self,
        items: Any = None,
        max_elements: Any = 200,
        time_budget_s: Any = 10,
        limit: Any = 100,
        offset: Any = 0,
        count_only: Any = False,
        fields: Any = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_get_parameters"
        try:
            if not isinstance(items, list) or not 1 <= len(items) <= 50:
                raise ValueError("items must be a list of 1 to 50 items")
            clean: List[Dict[str, Any]] = []
            for i, it in enumerate(items):
                what = f"items[{i}]"
                if isinstance(it, dict) and set(it) - {"id", "ids", "selector", "scope", "params"}:
                    raise ValueError(f"{what} has unknown keys: {', '.join(sorted(set(it) - {'id', 'ids', 'selector', 'scope', 'params'}))}")
                entry, _n = _selection(it, what, 2000)
                names = it.get("params") or []
                if not isinstance(names, list) or len(names) > 100:
                    raise ValueError(f"{what}.params must be a list of at most 100 parameter names (empty: all parameters)")
                entry["params"] = [_text(n, f"{what}.params[]") for n in names]
                clean.append(entry)
            args = {
                "items": clean,
                "max_elements": int(_bounded(max_elements, "max_elements", 200, 1, 2000)),
                "time_budget_s": _bounded(time_budget_s, "time_budget_s", 10.0, 1.0, 25.0),
            }
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        parsed, elapsed, early = _run(tool, "get_parameters.ipy", args, write=False, tool_executor=tool_executor, approved_executor=None)
        if early is not None or parsed is None:
            return early or {}
        result = assemble_result(
            tool,
            parsed,
            page,
            row_types=READ_TYPES,
            elapsed_ms=elapsed,
            workspace=workspace,
        )
        limits = result.get("limits") or {}
        result["truncated"] = bool(limits.get("truncated") or limits.get("partial"))
        return result

    # ---- write -------------------------------------------------------------- #
    def set_parameters(
        self,
        items: Any = None,
        on_error: Any = None,
        dry_run: Any = False,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_set_parameters"
        try:
            if not isinstance(items, list) or not 1 <= len(items) <= MAX_WRITE_ELEMENTS:
                raise ValueError(f"items must be a list of 1 to {MAX_WRITE_ELEMENTS} items")
            clean: List[Dict[str, Any]] = []
            total_ids = 0
            for i, it in enumerate(items):
                what = f"items[{i}]"
                if isinstance(it, dict) and set(it) - {"id", "ids", "selector", "scope", "params"}:
                    raise ValueError(f"{what} has unknown keys: {', '.join(sorted(set(it) - {'id', 'ids', 'selector', 'scope', 'params'}))}")
                entry, n = _selection(it, what, MAX_WRITE_ELEMENTS)
                total_ids += n
                params = it.get("params")
                if not isinstance(params, dict) or not 1 <= len(params) <= MAX_PARAMS_PER_ITEM:
                    raise ValueError(f"{what}.params must be an object of 1 to {MAX_PARAMS_PER_ITEM} parameter names and values")
                entry["params"] = {_text(name, f"{what}.params name"): _value(str(name), value, f"{what}.params") for name, value in params.items()}
                clean.append(entry)
            if total_ids > MAX_WRITE_ELEMENTS:
                raise ValueError(f"at most {MAX_WRITE_ELEMENTS} elements per call; this call lists {total_ids} ids")
            args = {
                "items": clean,
                "on_error": _choice(on_error, ("abort", "skip"), "on_error", "abort"),
                "dry_run": _flag(dry_run, "dry_run"),
                "max_elements": MAX_WRITE_ELEMENTS,
            }
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "set_parameters.ipy", args, write=True, tool_executor=None, approved_executor=approved_executor)
        if early is not None or parsed is None:
            return early or {}
        return _finish_write(tool, parsed, elapsed, workspace, dry_run=args["dry_run"])
