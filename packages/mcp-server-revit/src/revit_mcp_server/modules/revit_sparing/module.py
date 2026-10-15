"""
revit_sparing module - sparingen (openings where MEP passes through walls and floors) for a live Revit session.

Dutch contractor BIM teams model every penetration as a sparing: an opening family or a native opening with an
approval status, later copied into the discipline models (BIM Loket "Workflow sparingscoordinatie"). This module is
the first slice of that workflow.

Commands (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  find    read-only  where do ducts, pipes, conduits and cable trays cross walls, floors (and optionally roofs and
                     structural framing), in the active model and optionally in linked models; per crossing the size
                     of the MEP element, the host thickness, the passage angle, whether an opening is already there,
                     and a suggested sparing size (MEP size + clearance per side, rounded up)
  place     WRITE    place sparings at those crossings: an existing loaded sparing family ('family') or a native
                     opening ('opening'), sized, tagged and given an approval status

How it works: the same seam as ``revit_docs`` and ``revit_mep`` (read their module.py headers). Each command builds an
IronPython 2.7 script from the revit module's ``_prelude.ipy`` (line protocol), for ``place`` also the revit_docs
``_tags_read.ipy`` and ``_write_prelude.ipy`` (Runner, Collector, ownership tags: reused, not copied), then this
module's ``_sparing_detect.ipy`` (the detection, shared by both commands) and the command script. The arguments go in
as an ``ARGS`` literal, the script runs in Revit through revit_execute_python, and the printed line protocol becomes
the plan section 6 contract (``revit_mcp_server.check_contract``) with ``verified`` and ``limits.partial`` flags.

Detection (``_sparing_detect.ipy``): MEP elements are selected by category (and system, level or ids) and capped at
max_elements; hosts are collected with a bounding-box filter around the selected MEP only, so there is never an
unbounded model-wide scan. Broad phase: a grid of bounding boxes. Narrow phase: the MEP centre line against the host
solids (Solid.IntersectWithCurve). A host that is already cut by an opening has a hole there, so when the line misses
the solid the crossing of the host's mid plane is checked against existing openings and sparing families instead.
max_pairs and time_budget_s stop the work early; the result then says truncated/partial and is not verified.
Crossings of the same MEP run through the same host within merge_tolerance_mm become one sparing.

Safety of the write command (same rules as revit_docs):
  * ``is_mutating`` in module.json: the approval gate demands an approved plan_id first;
  * one TransactionGroup per call, one Transaction per sparing; on_error 'abort' (default) rolls the whole group back
    on the first failure and returns ok:false with the element ids and Revit's message; 'skip' keeps what worked;
    Revit warnings are dismissed and listed;
  * every sparing carries the Extensible Storage tag of revit_docs (tag, key = 'sparing:' + crossing_id, kind), so a
    re-run with the same tag replaces only the sparings it made itself; anything else at a crossing (a foreign opening
    or sparing) is left alone and the crossing is skipped, never duplicated;
  * a family whose size or status parameters are missing is refused before anything changes, with the list of the
    parameters it does have (a probe placement in a transaction that is always rolled back);
  * dry_run does all the work inside the group, reports it, then rolls everything back;
  * results carry ``changed_ids``, ``post_check`` (each sparing re-read: exists, tag, size, status, position) and
    ``verified``, and are never ``ok: true`` when a post-check fails.

Follow-ups (not built yet): the approval flow (status Voorstel -> Akkoord/Afgewezen, by whom, when), copying approved
sparingen into the discipline models (constructie / architectuur), an IFC or BCF hand-off of the proposals, sparing
families per shape (round core drill vs rectangular), bundling several runs into one sparing, sloped floors and roofs
(the frame assumes a horizontal floor), curved MEP runs and curved walls in the native opening mode.

UNVERIFIED: nothing here has run against a live Revit. The scripts are syntax-checked and exercised against a stub of
the Revit API (tests/revit_sparing_stub.py on top of revit_api_stub.py and revit_mep_stub.py), which proves the
control flow, the arithmetic, the budgets, ownership/replace rules, rollback and the line protocol, not that Revit
accepts the calls. Specifically unproven in a live model: Solid.IntersectWithCurve on wall and floor solids,
SolidUtils.CreateTransformed and RevitLinkInstance.GetTotalTransform for links, BoundingBoxIntersectsFilter outlines
in link coordinates, the size and insulation parameters read per category, connector BasisX as the duct width axis,
Opening bounding boxes, BasePoint.GetProjectBasePoint for project coordinates, the three NewFamilyInstance overloads
(face reference incl. CreateLinkReference, hosted, non-hosted plus RotateElement), NewOpening for walls and floors,
and the units of the family size parameters. Treat the first real run as a trial on a scratch model.
"""
from __future__ import annotations

import math
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from revit_mcp_server.check_contract import (
    MAX_LIMIT,
    PageSpec,
    ScriptOutput,
    assemble_result,
    error_result,
    is_safe_name,
    load_json,
    mock_result,
    parse_script_output,
    save_json,
)

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
REVIT_MODULE_DIR = MODULE_DIR.parent / "revit"
DOCS_SCRIPT_DIR = MODULE_DIR.parent / "revit_docs" / "scripts"
REVIT_PRELUDE = REVIT_MODULE_DIR / "scripts" / "_prelude.ipy"
TAGS_READ = DOCS_SCRIPT_DIR / "_tags_read.ipy"
WRITE_PRELUDE = DOCS_SCRIPT_DIR / "_write_prelude.ipy"
DETECT = "_sparing_detect.ipy"
EXECUTE_TOOL = "revit_execute_python"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

# script name -> write script?
SCRIPTS: Dict[str, bool] = {"find.ipy": False, "place.ipy": True}
# Shared source files loaded between the preludes and ARGS, per script (order matters). Every file holds definitions only.
PLACE_LIB = "_sparing_place_lib.ipy"
SCRIPT_PARTS: Dict[str, Tuple[str, ...]] = {"find.ipy": (DETECT,), "place.ipy": (DETECT, PLACE_LIB)}
# Scripts that read Extensible Storage tags even though they do not write.
READS_TAGS: Tuple[str, ...] = ()

MEP_CATEGORIES = ("pipes", "ducts", "conduits", "cabletrays")
HOST_CATEGORIES = ("walls", "floors", "roofs", "structuralframing")
_CATEGORY_ALIASES = {
    "pipe": "pipes", "pipes": "pipes", "duct": "ducts", "ducts": "ducts", "conduit": "conduits", "conduits": "conduits",
    "cabletray": "cabletrays", "cabletrays": "cabletrays", "wall": "walls", "walls": "walls", "floor": "floors",
    "floors": "floors", "roof": "roofs", "roofs": "roofs", "structuralframing": "structuralframing",
    "framing": "structuralframing", "beams": "structuralframing", "beam": "structuralframing",
}
SIZE_KEYS = ("width", "height", "depth", "diameter")

_TAG = re.compile(r"^[ -~]{1,80}$")  # printable ASCII only
_CROSSING_ID = re.compile(r"^[A-Za-z0-9.#x-]{1,80}$")
_BAD_NAME_CHARS = set("\\:{}[]|;<>?`~")

_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "family_not_found": "Load the sparing family into the project first and use the exact family and type names listed in the message. Nothing was changed.",
    "missing_parameter": "The family lacks the instance parameters named in size_parameters or status_parameter. Use names from the list in the message (or add the parameters to the family). Nothing was changed.",
    "placement_failed": "Revit could not place the first sparing (wrong placement type, no host face, host in a link for a hosted family). Nothing was changed.",
    "crossing_not_found": "Run revit_sparing_find with the same filters and use crossing_id values from its rows. Nothing was changed.",
    "too_many_sparings": "Narrow the call with level, system, ids or crossing_ids, or raise max_sparings (at most 500). Nothing was changed.",
    "nothing_to_place": "No crossing needs a sparing with these filters. Nothing was changed.",
    "rolled_back": "Nothing was changed: the whole call was rolled back. Fix the cause named in fails and call again, or pass on_error='skip' to keep what worked.",
    "partial_failure": "The sparings that worked were kept (see changed_ids); the failed ones are in fails with element ids. Run the same call again to replace what this tool made, or fix the cause first.",
    "post_check_failed": "The model changed but a check afterwards failed (see post_check). Inspect the listed ids, or run the call again to replace what this tool made.",
    "script_exception": "The embedded script failed inside Revit; any open transaction group was rolled back, so the model should be unchanged (verify with revit_warnings_delta).",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id, and do not repeat a write until it has finished.",
}


# --------------------------------------------------------------------------- #
# Script building and the seams to Revit (same shape as revit_docs / revit_mep)
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
    """Prelude(s) + detection + ``ARGS`` literal + the command script. The read script gets no write prelude."""
    write = SCRIPTS[script_name]
    parts = [REVIT_PRELUDE.read_text(encoding="utf-8")]
    if write or script_name in READS_TAGS:
        parts.append(TAGS_READ.read_text(encoding="utf-8"))
    if write:
        parts.append(WRITE_PRELUDE.read_text(encoding="utf-8"))
    for lib in SCRIPT_PARTS[script_name]:
        parts.append((SCRIPT_DIR / lib).read_text(encoding="utf-8"))
    parts.append(f"ARGS = {py2_literal(args)}")
    parts.append((SCRIPT_DIR / script_name).read_text(encoding="utf-8"))
    return "\n\n".join(parts) + "\n"


def run_read_script(script: str, tool_executor: ToolExecutor) -> Any:
    """Send a read-only script to Revit (mode 'read': no approval, cannot open a transaction)."""
    return tool_executor(EXECUTE_TOOL, {"script": script, "mode": "read"})


def run_write_script(script: str, approved_executor: ToolExecutor) -> Any:
    """Send a write script to Revit. Only revit_sparing_place calls this, with the executor the approval gate handed it."""
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
def _tag(value: Any) -> str:
    tag = str(value or "")
    if not _TAG.match(tag):
        raise ValueError("tag is required: 1-80 printable ASCII characters (your label for this batch of sparingen)")
    return tag


def _name(value: Any, what: str) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(f"{what} is required")
    if len(text) > 200:
        raise ValueError(f"{what} is longer than 200 characters")
    if any(ord(c) < 32 for c in text):
        raise ValueError(f"{what} contains control characters")
    bad = sorted(c for c in set(text) if c in _BAD_NAME_CHARS)
    if bad:
        raise ValueError(f"{what} contains characters Revit does not allow in names: {' '.join(bad)}")
    return text


def _opt_name(value: Any, what: str) -> str:
    return "" if value in (None, "") else _name(value, what)


def _text(value: Any, what: str) -> str:
    text = str(value if value is not None else "")
    if len(text) > 200 or any(ord(c) < 32 for c in text):
        raise ValueError(f"{what} must be at most 200 printable characters")
    return text


def _num(value: Any, what: str, lo: float, hi: float, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{what} must be a finite number")
    if not lo <= float(value) <= hi:
        raise ValueError(f"{what} must be between {lo:g} and {hi:g}")
    return float(value)


def _int(value: Any, what: str, lo: int, hi: int, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{what} must be an integer")
    if not lo <= int(value) <= hi:
        raise ValueError(f"{what} must be between {lo} and {hi}")
    return int(value)


def _bool(value: Any, what: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{what} must be true or false")
    return value


def _categories(value: Any, allowed: Tuple[str, ...], default: Tuple[str, ...], what: str) -> List[str]:
    if value in (None, []):
        return list(default)
    if not isinstance(value, list) or len(value) > 10:
        raise ValueError(f"{what} must be a list of category names: {', '.join(allowed)}")
    out: List[str] = []
    for v in value:
        key = _CATEGORY_ALIASES.get(str(v).lower().replace(" ", "").replace("_", ""))
        if key not in allowed:
            raise ValueError(f"{what}: unknown category {v!r}; use {', '.join(allowed)}")
        if key not in out:
            out.append(key)
    return out


def _choice(value: Any, allowed: Tuple[str, ...], what: str, default: Optional[str] = None) -> str:
    if value in (None, ""):
        if default is None:
            raise ValueError(f"{what} is required: one of {', '.join(allowed)}")
        return default
    if value not in allowed:
        raise ValueError(f"{what} must be one of {', '.join(allowed)}, got {value!r}")
    return str(value)


def _bad_input(tool: str, exc: Exception) -> Dict[str, Any]:
    return error_result(tool, "invalid_input", str(exc), hint=_HINTS["invalid_input"])


def detection_args(
    categories: Any = None,
    system: Any = None,
    level: Any = None,
    ids: Any = None,
    host_categories: Any = None,
    include_links: Any = None,
    sparing_family: Any = None,
    clearance_mm: Any = None,
    round_to_mm: Any = None,
    merge_tolerance_mm: Any = None,
    existing_tolerance_mm: Any = None,
    max_pairs: Any = None,
    max_elements: Any = None,
    time_budget_s: Any = None,
) -> Dict[str, Any]:
    """The validated detection arguments shared by find and place (raises ValueError)."""
    clean_ids: List[int] = []
    if ids not in (None, []):
        if not isinstance(ids, list) or len(ids) > 2000:
            raise ValueError("ids must be a list of at most 2000 element ids")
        for i in ids:
            clean_ids.append(_int(i, "ids", 1, 2**62, 0))
    return {
        "categories": _categories(categories, MEP_CATEGORIES, MEP_CATEGORIES, "categories"),
        "system": _text(system, "system").strip() if system not in (None, "") else "",
        "level": _opt_name(level, "level"),
        "ids": clean_ids,
        "host_categories": _categories(host_categories, HOST_CATEGORIES, ("walls", "floors"), "host_categories"),
        "include_links": _bool(include_links, "include_links", False),
        "sparing_family": _opt_name(sparing_family, "sparing_family"),
        "clearance_mm": _num(clearance_mm, "clearance_mm", 0.0, 500.0, 25.0),
        "round_to_mm": _num(round_to_mm, "round_to_mm", 1.0, 500.0, 10.0),
        "merge_tolerance_mm": _num(merge_tolerance_mm, "merge_tolerance_mm", 0.0, 2000.0, 100.0),
        "existing_tolerance_mm": _num(existing_tolerance_mm, "existing_tolerance_mm", 0.0, 1000.0, 50.0),
        "max_pairs": _int(max_pairs, "max_pairs", 1, 500000, 20000),
        "max_elements": _int(max_elements, "max_elements", 1, 20000, 2000),
        "time_budget_s": _num(time_budget_s, "time_budget_s", 1.0, 25.0, 15.0),
    }


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #
CROSSING_TYPES = {
    "mep_id": "int", "host_id": "int", "x_mm": "float", "y_mm": "float", "z_mm": "float", "insul_mm": "float",
    "host_t_mm": "float", "angle_deg": "float", "sparing_w_mm": "int", "sparing_h_mm": "int", "sparing_d_mm": "int",
    "members": "int", "existing_id": "int",
}
ITEM_TYPES = {"id": "int", "host_id": "int", "w_mm": "int", "h_mm": "int", "d_mm": "int"}
TOTAL_KEYS = ("crossings", "need_sparing", "already_open", "mep_elements", "hosts", "pairs_tested", "parallel_in_host", "skipped_elements")


def _totals(meta: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in TOTAL_KEYS:
        try:
            out[key] = int(meta.get(key, "0") or 0)
        except ValueError:
            out[key] = 0
    out["truncated"] = meta.get("truncated", "0") == "1"
    if meta.get("truncated_reason"):
        out["truncated_reason"] = meta["truncated_reason"]
    out["coordinates"] = meta.get("coordinates", "")
    return out


def _summary_first(result: Dict[str, Any], totals: Dict[str, Any]) -> Dict[str, Any]:
    """Compact output: verdict and counts first, the rows last."""
    head = ("ok", "tool", "verified", "summary")
    ordered: Dict[str, Any] = {k: result[k] for k in head if k in result}
    ordered["totals"] = totals
    for k, v in result.items():
        if k not in ordered and k != "rows":
            ordered[k] = v
    if "rows" in result:
        ordered["rows"] = result["rows"]
    return ordered


def _finish_write(
    tool: str,
    parsed: ScriptOutput,
    elapsed: int,
    workspace: Any,
    *,
    item_types: Optional[Dict[str, str]] = None,
    extra: Optional[Dict[str, Any]] = None,
    dry_run_asked: bool = False,
) -> Dict[str, Any]:
    outcome = parsed.meta.get("outcome", "ok")
    # a dry run is reported either by the script's own close ('dry_run') or by the Runner's built-in one (dry_run=1)
    dry_run = outcome == "dry_run" or (outcome == "ok" and parsed.meta.get("dry_run") == "1")
    if dry_run:
        outcome = "dry_run"
    changed = _ints(parsed.meta.get("changed_ids"))
    failed_ids = _ints(parsed.meta.get("failed_ids"))
    violation = ""
    if dry_run_asked and not dry_run and changed and outcome in ("ok", "partial_failure", "post_check_failed"):
        violation = "DRY_RUN_NOT_HONOURED: a dry run was asked for but the script reports committed changes; check the model"
    posts = [r for r in parsed.rows if r.get("row_type") == "post"]
    items = [{k: v for k, v in r.items() if k != "row_type"} for r in parsed.rows if r.get("row_type") == "item"]
    checks = [{"check": r.get("check"), "ok": r.get("ok") == "1", "detail": r.get("detail", "")} for r in posts]
    checks.sort(key=lambda c: c["ok"])  # failures first
    failed_checks = sum(1 for c in checks if not c["ok"])
    post_check = {"ok": failed_checks == 0, "checked": len(checks), "failed": failed_checks, "checks": checks[:40]}
    if outcome == "ok" and not post_check["ok"]:
        outcome = "post_check_failed"
    fails = list(parsed.fails)
    if violation:
        fails.insert(0, violation)
        outcome = "dry_run_not_honoured"

    synthetic = ScriptOutput(
        summary=parsed.summary,
        fails=fails,
        infos=list(parsed.infos),
        rows=items,
        meta=dict(parsed.meta),
        counts={"fail": parsed.counts.get("fail", len(parsed.fails)) + (1 if violation else 0), "info": parsed.counts.get("info", len(parsed.infos)), "row": len(items)},
    )
    fields: Dict[str, Any] = {
        "changed_ids": changed if outcome in ("ok", "partial_failure", "post_check_failed") else [],
        "post_check": post_check,
        "outcome": outcome,
        "dry_run": dry_run,
        "on_error": parsed.meta.get("on_error"),
        "warnings_dismissed": int(parsed.meta.get("warnings_dismissed", "0") or 0),
    }
    if dry_run and parsed.meta.get("would_change_ids"):
        fields["would_change_ids"] = _ints(parsed.meta.get("would_change_ids"))
    if extra:
        fields.update(extra)
    ok = outcome in ("ok", "dry_run") and post_check["ok"] and not fails and parsed.counts.get("fail", 0) == 0
    summary = parsed.summary
    failed_text = [c for c in checks if not c["ok"]]
    if not ok:
        first = fails[0] if fails else (
            ("%s: %s" % (failed_text[0]["check"], failed_text[0]["detail"])) if failed_text else outcome)
        summary = f"FAILED ({outcome}): {first}"
        if outcome == "rolled_back":
            summary += " The whole call was rolled back; the model is unchanged."
    elif dry_run:
        summary = "DRY RUN (everything was rolled back, the model is unchanged): " + summary
    result = assemble_result(
        tool, synthetic, PageSpec(limit=MAX_LIMIT), row_types=item_types or ITEM_TYPES, elapsed_ms=elapsed, workspace=workspace,
        summary=summary, extra=fields,
    )
    if dry_run:
        result["verified"] = False
    if not ok:
        result["ok"] = False
        result["kind"] = outcome if outcome not in ("ok", "dry_run") else "post_check_failed"
        if fails:
            result["message"] = fails[0]
        elif failed_text:
            result["message"] = "%s: %s" % (failed_text[0]["check"], failed_text[0]["detail"])
        else:
            result["message"] = f"outcome: {outcome}"
        result["element_ids"] = failed_ids
        result["hint"] = _HINTS.get(result["kind"], "")
    return _summary_first(result, _totals(parsed.meta))


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
class RevitSparingModule:

    # ---- read-only ---------------------------------------------------------- #
    def find(
        self,
        categories: Any = None,
        system: Any = None,
        level: Any = None,
        ids: Any = None,
        host_categories: Any = None,
        include_links: Any = None,
        sparing_family: Any = None,
        clearance_mm: Any = None,
        round_to_mm: Any = None,
        merge_tolerance_mm: Any = None,
        existing_tolerance_mm: Any = None,
        max_pairs: Any = None,
        max_elements: Any = None,
        time_budget_s: Any = None,
        limit: Any = None,
        offset: Any = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_find"
        try:
            args = detection_args(categories, system, level, ids, host_categories, include_links, sparing_family,
                                  clearance_mm, round_to_mm, merge_tolerance_mm, existing_tolerance_mm, max_pairs,
                                  max_elements, time_budget_s)
            page = PageSpec(limit=_int(limit, "limit", 1, MAX_LIMIT, 200), offset=_int(offset, "offset", 0, 10**7, 0))
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "find.ipy", args, write=False, tool_executor=tool_executor, approved_executor=None)
        if early is not None or parsed is None:
            return early or {}
        result = assemble_result(tool, parsed, page, row_types=CROSSING_TYPES, elapsed_ms=elapsed, workspace=workspace)
        totals = _totals(parsed.meta)
        if totals["truncated"]:
            result["limits"]["truncated"] = True
            result["limits"]["partial"] = True
        return _summary_first(result, totals)

    # ---- write -------------------------------------------------------------- #
    def place(
        self,
        tag: Any = None,
        mode: Any = None,
        family_name: Any = None,
        type_name: Any = None,
        size_parameters: Any = None,
        status_parameter: Any = None,
        status_value: Any = None,
        crossing_ids: Any = None,
        max_sparings: Any = None,
        on_error: Any = None,
        dry_run: Any = None,
        categories: Any = None,
        system: Any = None,
        level: Any = None,
        ids: Any = None,
        host_categories: Any = None,
        include_links: Any = None,
        sparing_family: Any = None,
        clearance_mm: Any = None,
        round_to_mm: Any = None,
        merge_tolerance_mm: Any = None,
        existing_tolerance_mm: Any = None,
        max_pairs: Any = None,
        max_elements: Any = None,
        time_budget_s: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_place"
        try:
            m = _choice(mode, ("family", "opening"), "mode")
            args: Dict[str, Any] = {"tag": _tag(tag), "mode": m}
            if m == "family":
                args["family_name"] = _name(family_name, "family_name")
                args["type_name"] = _name(type_name, "type_name")
                args["size_parameters"] = self._size_parameters(size_parameters)
            else:
                if family_name not in (None, "") or type_name not in (None, "") or size_parameters not in (None, {}):
                    raise ValueError("family_name, type_name and size_parameters belong to mode 'family'; leave them out for mode 'opening'")
                args["family_name"], args["type_name"], args["size_parameters"] = "", "", {}
            args["status_parameter"] = _opt_name(status_parameter, "status_parameter")
            if args["status_parameter"]:
                args["status_value"] = _text(status_value if status_value not in (None, "") else "Voorstel", "status_value")
            elif status_value not in (None, ""):
                raise ValueError("status_value needs status_parameter (the text parameter to write it to)")
            else:
                args["status_value"] = ""
            cids: List[str] = []
            if crossing_ids not in (None, []):
                if not isinstance(crossing_ids, list) or len(crossing_ids) > 500:
                    raise ValueError("crossing_ids must be a list of at most 500 crossing_id values from revit_sparing_find")
                for c in crossing_ids:
                    if not isinstance(c, str) or not _CROSSING_ID.match(c):
                        raise ValueError(f"crossing_ids: {c!r} is not a crossing_id (copy it from revit_sparing_find)")
                    if c not in cids:
                        cids.append(c)
            args["crossing_ids"] = cids
            args["max_sparings"] = _int(max_sparings, "max_sparings", 1, 500, 100)
            args["on_error"] = _choice(on_error, ("abort", "skip"), "on_error", "abort")
            args["dry_run"] = _bool(dry_run, "dry_run", False)
            fam = sparing_family if sparing_family not in (None, "") else (args["family_name"] or None)
            args.update(detection_args(categories, system, level, ids, host_categories, include_links, fam,
                                       clearance_mm, round_to_mm, merge_tolerance_mm, existing_tolerance_mm, max_pairs,
                                       max_elements, time_budget_s))
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "place.ipy", args, write=True, tool_executor=None, approved_executor=approved_executor)
        if early is not None or parsed is None:
            return early or {}
        return _finish_write(tool, parsed, elapsed, workspace, dry_run_asked=args["dry_run"])

    @staticmethod
    def _size_parameters(value: Any) -> Dict[str, str]:
        if not isinstance(value, dict) or not value:
            raise ValueError("size_parameters is required for mode 'family': a map such as {\"width\": \"b\", \"height\": \"h\", \"depth\": \"d\"} (or diameter) to the family's instance parameter names")
        unknown = set(value) - set(SIZE_KEYS)
        if unknown:
            raise ValueError(f"size_parameters has unknown keys: {', '.join(sorted(unknown))}; use {', '.join(SIZE_KEYS)}")
        out = {k: _name(v, f"size_parameters.{k}") for k, v in value.items() if v not in (None, "")}
        if not (("width" in out and "height" in out) or "diameter" in out):
            raise ValueError("size_parameters needs width and height, or diameter")
        return out
