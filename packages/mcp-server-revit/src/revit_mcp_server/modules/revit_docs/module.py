"""
revit_docs module - documentation automation for a live Revit session (plan items 1.10, 2.6, 2.7 and the
documentation tools of section 13 of docs/upgrade-plan-hands-and-eyes.md).

Commands (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  list_views_sheets_schedules  read-only  counts, names, ids, templates, sheet placement, unplaced views
  render_check                 read-only  export one view to PNG, return the real path, bytes, size and a looks_blank flag
  make_view                    WRITE      3D (fitted section box, ShadingWithEdges), plan, section, elevation, view template by name
  make_sheet                   WRITE      sheet with a title block by name, views placed on a grid
  make_schedule                WRITE      schedule with fields, filters, sorting, totals; optionally placed on a sheet
  export                       WRITE      PDF, DWG, IFC, NWC to a path inside the workspace sandbox

How it works: like the ``revit`` module, each command builds an IronPython 2.7 script from the revit module's
``_prelude.ipy`` plus this module's scripts, injects the arguments as an ``ARGS`` literal and runs it in Revit; the
script prints the tab-separated line protocol that ``revit_mcp_server.check_contract`` turns into the plan section 6
contract. The three seams to Revit are ``run_read_script`` (read mode, no approval), ``run_write_script`` (write mode,
only for the write commands) and the ``revit_export_image`` call of render_check.

Safety of the write commands:
  * they are ``is_mutating`` in module.json, so the approval gate demands an approved plan_id before they start;
    that one approval covers the vetted scripts they build (ModuleProvider hands them ``approved_executor``, which
    can call revit_execute_python only);
  * every run happens in one TransactionGroup, every element in its own Transaction; on_error 'abort' (default) rolls
    the whole group back on the first failure, 'skip' keeps what worked;
  * the tools replace only elements that carry their own Extensible Storage tag (tag + key + kind) and never rename,
    modify or delete anything else; a level's own plan view is never renamed;
  * the result always carries ``changed_ids`` and a ``post_check`` section, and is never ``ok: true`` when a post-check failed.

Everything that needs a running Revit is UNVERIFIED here: the scripts are syntax-checked and exercised against a
stub of the Revit API in the tests (tests/test_revit_docs.py), not against Revit.
"""
from __future__ import annotations

import math
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from revit_mcp_server.check_contract import (
    PageSpec,
    ScriptOutput,
    assemble_result,
    error_result,
    mock_result,
    parse_script_output,
)
from revit_mcp_server.image_check import analyze_png

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
# The line protocol, select_elements and the other read-only helpers are shared with the revit module.
REVIT_PRELUDE = MODULE_DIR.parent / "revit" / "scripts" / "_prelude.ipy"
TAGS_READ = "_tags_read.ipy"
WRITE_PRELUDE = "_write_prelude.ipy"
EXECUTE_TOOL = "revit_execute_python"
EXPORT_IMAGE_TOOL = "revit_export_image"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

_TAG = re.compile(r"^[ -~]{1,80}$")  # printable ASCII only
_BAD_NAME_CHARS = set("\\:{}[]|;<>?`~")
KIND_ORDER = {"view": 0, "sheet": 1, "schedule": 2, "template": 3}
EXPORT_EXT = {"pdf": ".pdf", "dwg": ".dwg", "ifc": ".ifc", "nwc": ".nwc"}

_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "path_outside_workspace": "Use a path inside the allowed workspace directories (see revit_get_context for the workspace folder).",
    "name_conflict": "Choose another name. This tool replaces only elements it made under the same tag and name, and never touches others; delete or rename the existing one yourself if it is really yours.",
    "number_conflict": "Choose another sheet number, or delete the existing sheet yourself. This tool never touches sheets it did not make.",
    "template_not_found": "Use one of the view template names listed in the message (revit_list_views_sheets_schedules with kinds ['templates']).",
    "title_block_not_found": "Use one of the title block type names listed in the message.",
    "view_not_found": "Check the view ids or names with revit_list_views_sheets_schedules.",
    "view_already_placed": "A view can be on one sheet only. Remove its viewport from the other sheet yourself or make a duplicate view first; this tool never moves a placed view.",
    "level_not_found": "List the levels with revit_list_levels and use the exact name.",
    "sheet_not_found": "Make the sheet first with revit_make_sheet, then pass its number.",
    "sheet_not_owned": "Pass allow_foreign=true to add the schedule to a sheet this tool did not make.",
    "rolled_back": "Nothing was changed: the whole call was rolled back. Fix the cause named in fails and call again, or pass on_error='skip' to keep what worked.",
    "partial_failure": "The steps that worked were kept (see changed_ids); the failed ones are in fails with element ids. Run the same call again to replace what this tool made, or fix the cause first.",
    "post_check_failed": "The model changed but a check afterwards failed (see post_check). Run the call again, or inspect the listed ids.",
    "file_exists": "Pass overwrite=true to replace the file, or choose another path.",
    "exporter_unavailable": "The Navisworks exporter add-in must be installed in this Revit for NWC export; use ifc instead.",
    "export_failed": "Revit refused the export. Check the options (sheet numbers, view ids) and that the folder is writable.",
    "script_exception": "The embedded script failed inside Revit; any open transaction group was rolled back, so the model should be unchanged (verify with revit_warnings_delta).",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id, and do not repeat a write until it has finished.",
}


# --------------------------------------------------------------------------- #
# Script building and the seams to Revit
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


def build_script(script_name: str, args: Dict[str, Any], *, write: bool) -> str:
    """Revit prelude + tag helpers (+ write prelude) + ``ARGS`` literal + the tool script."""
    parts = [REVIT_PRELUDE.read_text(encoding="utf-8"), (SCRIPT_DIR / TAGS_READ).read_text(encoding="utf-8")]
    if write:
        parts.append((SCRIPT_DIR / WRITE_PRELUDE).read_text(encoding="utf-8"))
    parts.append(f"ARGS = {py2_literal(args)}")
    parts.append((SCRIPT_DIR / script_name).read_text(encoding="utf-8"))
    return "\n\n".join(parts) + "\n"


def run_read_script(script: str, tool_executor: ToolExecutor) -> Any:
    """Send a read-only script to Revit (mode 'read': no approval, cannot open a transaction)."""
    return tool_executor(EXECUTE_TOOL, {"script": script, "mode": "read"})


def run_write_script(script: str, approved_executor: ToolExecutor) -> Any:
    """Send a write script to Revit. Only the write commands call this, with the executor the approval gate handed them."""
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
    script = build_script(script_name, script_args, write=write)
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


# --------------------------------------------------------------------------- #
# Argument helpers
# --------------------------------------------------------------------------- #
def _tag(value: Any) -> str:
    tag = str(value or "")
    if not _TAG.match(tag):
        raise ValueError("tag is required: 1-80 printable ASCII characters (your label for this build phase)")
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
    return _name(value, what) if value not in (None, "") else ""


def _num(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{what} must be a finite number")
    return float(value)


def _num_list(value: Any, what: str, size: int) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{what} must be a list of {size} numbers")
    return [_num(v, what) for v in value]


def _int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{what} must be an integer")
    return int(value)


def _int_list(value: Any, what: str) -> List[int]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{what} must be a list of integers")
    return [_int(v, what) for v in value]


def _choice(value: Any, allowed: Tuple[str, ...], what: str, default: Optional[str] = None) -> str:
    if value in (None, ""):
        if default is None:
            raise ValueError(f"{what} is required: one of {', '.join(allowed)}")
        return default
    if value not in allowed:
        raise ValueError(f"{what} must be one of {', '.join(allowed)}, got {value!r}")
    return str(value)


def _scope(value: Any) -> Dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError("scope must be an object with ids, tag or categories")
    tag = str(value.get("tag") or "")
    if tag and not _TAG.match(tag):
        raise ValueError("scope.tag must be 1-80 printable ASCII characters")
    cats = value.get("categories") or []
    if not isinstance(cats, list):
        raise ValueError("scope.categories must be a list of names")
    return {"ids": _int_list(value.get("ids"), "scope.ids"), "tag": tag, "categories": [str(c) for c in cats]}


def _bad_input(tool: str, exc: Exception) -> Dict[str, Any]:
    return error_result(tool, "invalid_input", str(exc), hint=_HINTS["invalid_input"])


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #
ITEM_TYPES = {
    "id": "int", "view_id": "int", "fields": "int", "filters": "int", "sort": "int", "body_rows": "int",
    "x_mm": "float", "y_mm": "float", "width_mm": "float", "height_mm": "float", "bytes": "int", "exists": "bool",
}


def _finish_write(
    tool: str,
    parsed: ScriptOutput,
    elapsed: int,
    workspace: Any,
    *,
    extra: Optional[Dict[str, Any]] = None,
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

    synthetic = ScriptOutput(
        summary=parsed.summary,
        fails=list(parsed.fails),
        infos=list(parsed.infos),
        rows=items,
        meta=dict(parsed.meta),
        counts={"fail": parsed.counts.get("fail", len(parsed.fails)), "info": parsed.counts.get("info", len(parsed.infos)), "row": len(items)},
    )
    fields: Dict[str, Any] = {
        "changed_ids": changed if outcome in ("ok", "partial_failure", "post_check_failed") else [],
        "post_check": post_check,
        "outcome": outcome,
        "on_error": parsed.meta.get("on_error"),
        "warnings_dismissed": int(parsed.meta.get("warnings_dismissed", "0") or 0),
    }
    if extra:
        fields.update(extra)
    ok = outcome == "ok" and post_check["ok"] and not parsed.fails and parsed.counts.get("fail", 0) == 0
    summary = parsed.summary
    if not ok:
        first = parsed.fails[0] if parsed.fails else outcome
        summary = f"FAILED ({outcome}): {first}"
        if outcome == "rolled_back":
            summary += " The whole call was rolled back; the model is unchanged."
    result = assemble_result(
        tool,
        synthetic,
        PageSpec(),
        row_types=ITEM_TYPES,
        elapsed_ms=elapsed,
        workspace=workspace,
        summary=summary,
        extra=fields,
    )
    if not ok:
        result["ok"] = False
        result["kind"] = outcome if outcome != "ok" else "post_check_failed"
        result["message"] = parsed.fails[0] if parsed.fails else f"outcome: {outcome}"
        result["element_ids"] = failed_ids
        result["hint"] = _HINTS.get(result["kind"], "")
    return result


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
class RevitDocsModule:

    # ---- read-only ---------------------------------------------------------- #
    def list_views_sheets_schedules(
        self,
        kinds: Optional[List[str]] = None,
        name_contains: str = "",
        only_unplaced: bool = False,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_list_views_sheets_schedules"
        allowed = ("views", "sheets", "schedules", "templates")
        try:
            wanted = list(kinds) if kinds else list(allowed)
            for k in wanted:
                _choice(k, allowed, "kinds")
            needle = str(name_contains or "")
            if len(needle) > 100:
                raise ValueError("name_contains is longer than 100 characters")
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        args = {"kinds": wanted, "name_contains": needle, "only_unplaced": bool(only_unplaced)}
        parsed, elapsed, early = _run(tool, "list_views_sheets_schedules.ipy", args, write=False, tool_executor=tool_executor, approved_executor=None)
        if early is not None or parsed is None:
            return early or {}
        meta = parsed.meta
        counts = {
            "views": int(meta.get("n_views", 0) or 0),
            "views_not_on_a_sheet": int(meta.get("n_unplaced", 0) or 0),
            "sheets": int(meta.get("n_sheets", 0) or 0),
            "schedules": int(meta.get("n_schedules", 0) or 0),
            "view_templates": int(meta.get("n_templates", 0) or 0),
        }
        return assemble_result(
            tool,
            parsed,
            page,
            row_types={"id": "int", "placed": "bool", "views": "int"},
            sort_key=lambda r: (KIND_ORDER.get(str(r.get("kind")), 9), str(r.get("name") or "").lower()),
            elapsed_ms=elapsed,
            workspace=workspace,
            extra={"document_counts": counts},
        )

    def render_check(
        self,
        view_id: Any = None,
        output_path: Any = None,
        width: Any = 1000,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_render_check"
        try:
            vid = _int(view_id, "view_id")
            px = _int(width if width is not None else 1000, "width")
            if not 200 <= px <= 4000:
                raise ValueError("width must be between 200 and 4000 pixels")
            if not isinstance(output_path, str) or not output_path.strip():
                raise ValueError("output_path is required")
            target = Path(output_path)
            if target.suffix.lower() != ".png":
                raise ValueError("output_path must end in .png")
            target = _in_workspace(workspace, target)
        except _OutsideWorkspace as exc:
            return error_result(tool, "path_outside_workspace", str(exc), hint=_HINTS["path_outside_workspace"])
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        if _server_in_mock_mode():
            return mock_result(tool)
        if tool_executor is None:
            return error_result(tool, "no_bridge", "No connection to the Revit tools in this session.", hint="This tool must run inside the AEC Model Bridge server.")

        started = time.perf_counter()
        t0 = time.time() - 2.0
        try:
            raw = tool_executor(EXPORT_IMAGE_TOOL, {"view_id": vid, "output_path": str(target), "width": px})
        except Exception as exc:  # noqa: BLE001
            return _bridge_failure(tool, exc)
        elapsed = int((time.perf_counter() - started) * 1000)
        if _is_mock(raw):
            return mock_result(tool)
        if _is_running(raw):
            return _running(tool, raw)
        data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) and "file_path" not in raw else raw
        if not isinstance(data, dict):
            return error_result(tool, "bridge_error", f"unexpected answer from the bridge: {type(raw).__name__}")
        reported = data.get("file_path") or data.get("expected_file_path")
        found_by = "addin"
        candidate = Path(str(reported)) if reported else None
        if candidate is None or not candidate.is_file():
            candidate, found_by = _newest_png(target, t0), "scan"
        addin_error = data.get("error") or (data.get("message") if data.get("status") == "error" else None)
        if candidate is None or not candidate.is_file():
            return error_result(
                tool,
                "export_failed",
                str(addin_error or "Revit reported no image file and none was found next to the requested path."),
                hint="Open the view once in Revit (a never-opened view can export nothing), check the view id with revit_list_views_sheets_schedules, and that the folder is writable.",
            )
        try:
            candidate = _in_workspace(workspace, candidate)
        except _OutsideWorkspace as exc:
            return error_result(tool, "path_outside_workspace", f"Revit wrote the image to {candidate}: {exc}", hint=_HINTS["path_outside_workspace"])
        analysis = analyze_png(candidate)
        fails: List[str] = []
        infos: List[str] = []
        if analysis["bytes"] == 0:
            fails.append("IMAGE_EMPTY: the file has 0 bytes")
        if analysis["looks_blank"]:
            fails.append(
                "IMAGE_BLANK: %.1f%% of the pixels are one colour; the view shows (almost) nothing. "
                "Check the view's visibility, crop and section box, or frame it with revit_make_view." % (100.0 * analysis["dominant_fraction"])
            )
        if analysis["analysis_error"]:
            infos.append("NOT_ANALYSED: " + analysis["analysis_error"])
        if found_by == "scan":
            infos.append("PATH_FOUND_BY_SCAN: the add-in did not report the file path (older build?); used the newest PNG next to the requested path")
        if str(candidate) != str(target):
            infos.append("PATH_DIFFERS: Revit appends the view name to the file name; real path is %s" % candidate)
        size = f"{analysis['width']}x{analysis['height']} px" if analysis["width"] else "size unknown"
        verdict = "blank" if analysis["looks_blank"] else ("not analysed" if analysis["looks_blank"] is None else "has content")
        return {
            "ok": True,
            "tool": tool,
            "verified": analysis["looks_blank"] is not None and not analysis["analysis_error"],
            "build": None,
            "document": {"title": None, "guid": None},
            "elapsed_ms": elapsed,
            "summary": f"{candidate.name}: {size}, {analysis['bytes']} bytes, {verdict}",
            "fails": fails,
            "info": infos,
            "view_id": vid,
            "requested_path": str(target),
            "path": str(candidate),
            "bytes": analysis["bytes"],
            "exists": True,
            "width": analysis["width"],
            "height": analysis["height"],
            "looks_blank": analysis["looks_blank"],
            "dominant_fraction": analysis["dominant_fraction"],
            "content_fraction": analysis["content_fraction"],
            "distinct_colors": analysis["distinct_colors"],
            "luminance_histogram": analysis["luminance_histogram"],
            "changed_ids": [],
            "detail_file": None,
            "limits": {"truncated": False, "partial": analysis["looks_blank"] is None or bool(analysis["analysis_error"])},
        }

    # ---- write -------------------------------------------------------------- #
    def make_view(
        self,
        kind: Any = None,
        name: Any = None,
        tag: Any = None,
        template: Any = None,
        level: Any = None,
        plan_type: Any = None,
        scope: Any = None,
        margin_m: Any = 0.5,
        direction: Any = None,
        display_style: Any = None,
        p0: Any = None,
        p1: Any = None,
        z_bottom_m: Any = None,
        z_top_m: Any = None,
        depth_m: Any = 10.0,
        flip: Any = False,
        point: Any = None,
        facing: Any = None,
        on_error: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_make_view"
        try:
            k = _choice(kind, ("3d", "plan", "section", "elevation"), "kind")
            args: Dict[str, Any] = {
                "kind": k,
                "name": _name(name, "name"),
                "tag": _tag(tag),
                "template": _opt_name(template, "template"),
                "level": _opt_name(level, "level"),
                "plan_type": _choice(plan_type, ("floor", "ceiling"), "plan_type", "floor"),
                "scope": _scope(scope),
                "margin_m": max(0.0, _num(margin_m if margin_m is not None else 0.5, "margin_m")),
                "display_style": _choice(display_style, ("shaded_with_edges", "shaded", "hidden_line", "wireframe", "realistic", "consistent_colors", "keep"), "display_style", "") or None,
                "on_error": _choice(on_error, ("abort", "skip"), "on_error", "abort"),
            }
            if k in ("plan", "elevation") and not args["level"]:
                raise ValueError(f"level is required for kind {k}")
            if direction is not None:
                d = _num_list(direction, "direction", 3)
                if not any(abs(v) > 1e-9 for v in d):
                    raise ValueError("direction must not be the zero vector")
                args["direction"] = d
            if k == "section":
                args["p0"] = _num_list(p0, "p0", 2)
                args["p1"] = _num_list(p1, "p1", 2)
                if abs(args["p0"][0] - args["p1"][0]) + abs(args["p0"][1] - args["p1"][1]) < 1e-6:
                    raise ValueError("p0 and p1 are the same point; a section needs a line")
                args["z_bottom_m"] = _num(z_bottom_m, "z_bottom_m")
                args["z_top_m"] = _num(z_top_m, "z_top_m")
                if args["z_top_m"] <= args["z_bottom_m"]:
                    raise ValueError("z_top_m must be above z_bottom_m")
                args["depth_m"] = _num(depth_m if depth_m is not None else 10.0, "depth_m")
                if args["depth_m"] <= 0:
                    raise ValueError("depth_m must be positive")
                args["flip"] = bool(flip)
            if k == "elevation":
                args["point"] = _num_list(point, "point", 2)
                args["facing"] = _choice(facing, ("north", "south", "east", "west"), "facing")
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        return self._write(tool, "make_view.ipy", args, workspace, approved_executor)

    def make_sheet(
        self,
        number: Any = None,
        name: Any = None,
        tag: Any = None,
        title_block: Any = None,
        views: Any = None,
        columns: Any = None,
        margin_mm: Any = 15.0,
        gutter_mm: Any = 10.0,
        area_mm: Any = None,
        on_error: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_make_sheet"
        try:
            specs: List[Dict[str, Any]] = []
            if views is not None and not isinstance(views, list):
                raise ValueError("views must be a list")
            if len(views or []) > 60:
                raise ValueError("at most 60 views per sheet")
            for i, v in enumerate(views or []):
                if not isinstance(v, dict):
                    raise ValueError(f"views[{i}] must be an object with view_id or view_name")
                spec: Dict[str, Any] = {}
                if v.get("view_id") is not None:
                    spec["view_id"] = _int(v["view_id"], f"views[{i}].view_id")
                elif v.get("view_name"):
                    spec["view_name"] = str(v["view_name"])
                else:
                    raise ValueError(f"views[{i}] needs view_id or view_name")
                if (v.get("x_mm") is None) != (v.get("y_mm") is None):
                    raise ValueError(f"views[{i}]: give both x_mm and y_mm, or neither")
                if v.get("x_mm") is not None:
                    spec["x_mm"] = _num(v["x_mm"], f"views[{i}].x_mm")
                    spec["y_mm"] = _num(v["y_mm"], f"views[{i}].y_mm")
                specs.append(spec)
            args: Dict[str, Any] = {
                "number": _name(number, "number"),
                "name": _name(name, "name"),
                "tag": _tag(tag),
                "title_block": _opt_name(title_block, "title_block") if title_block else "",
                "views": specs,
                "columns": _int(columns, "columns") if columns is not None else None,
                "margin_mm": _num(margin_mm if margin_mm is not None else 15.0, "margin_mm"),
                "gutter_mm": _num(gutter_mm if gutter_mm is not None else 10.0, "gutter_mm"),
                "area_mm": None,
                "on_error": _choice(on_error, ("abort", "skip"), "on_error", "abort"),
            }
            if args["columns"] is not None and not 1 <= args["columns"] <= 12:
                raise ValueError("columns must be between 1 and 12")
            if not 0 <= args["margin_mm"] <= 300 or not 0 <= args["gutter_mm"] <= 300:
                raise ValueError("margin_mm and gutter_mm must be between 0 and 300")
            if area_mm is not None:
                a = _num_list(area_mm, "area_mm", 4)
                if a[2] <= a[0] or a[3] <= a[1]:
                    raise ValueError("area_mm must be [x0, y0, x1, y1] with x1 > x0 and y1 > y0")
                args["area_mm"] = a
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        return self._write(tool, "make_sheet.ipy", args, workspace, approved_executor)

    def make_schedule(
        self,
        name: Any = None,
        tag: Any = None,
        category: Any = None,
        fields: Any = None,
        filters: Any = None,
        sort: Any = None,
        totals: Any = None,
        grand_total: Any = False,
        itemize: Any = True,
        template: Any = None,
        sheet: Any = None,
        on_error: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_make_schedule"
        ops = ("equals", "not_equals", "greater", "greater_or_equal", "less", "less_or_equal", "contains", "not_contains",
               "begins_with", "not_begins_with", "ends_with", "not_ends_with", "has_value", "has_no_value")
        try:
            if not isinstance(fields, list) or not fields or len(fields) > 60:
                raise ValueError("fields must be a list of 1 to 60 field names")
            names = [_name(f, "fields[]") for f in fields]
            flt: List[Dict[str, Any]] = []
            for i, f in enumerate(filters or []):
                if not isinstance(f, dict):
                    raise ValueError(f"filters[{i}] must be an object with field, op and value")
                op = _choice(f.get("op"), ops, f"filters[{i}].op")
                entry: Dict[str, Any] = {"field": _name(f.get("field"), f"filters[{i}].field"), "op": op}
                if op not in ("has_value", "has_no_value"):
                    v = f.get("value")
                    if v is None or isinstance(v, (dict, list)):
                        raise ValueError(f"filters[{i}].value must be text or a number")
                    if isinstance(v, float) and not math.isfinite(v):
                        raise ValueError(f"filters[{i}].value must be finite")
                    entry["value"] = v
                flt.append(entry)
            srt: List[Dict[str, Any]] = []
            for i, s in enumerate(sort or []):
                if not isinstance(s, dict):
                    raise ValueError(f"sort[{i}] must be an object with field")
                srt.append({
                    "field": _name(s.get("field"), f"sort[{i}].field"),
                    "order": _choice(s.get("order"), ("ascending", "descending"), f"sort[{i}].order", "ascending"),
                    "header": bool(s.get("header")),
                    "footer": bool(s.get("footer")),
                    "blank_line": bool(s.get("blank_line")),
                })
            tot = [_name(t, "totals[]") for t in (totals or [])]
            missing = [t for t in tot if t.lower() not in {n.lower() for n in names}]
            if missing:
                raise ValueError("totals must name columns listed in fields; not in fields: " + ", ".join(missing))
            args: Dict[str, Any] = {
                "name": _name(name, "name"),
                "tag": _tag(tag),
                "category": _name(category, "category"),
                "fields": names,
                "filters": flt,
                "sort": srt,
                "totals": tot,
                "grand_total": bool(grand_total),
                "itemize": True if itemize is None else bool(itemize),
                "template": _opt_name(template, "template"),
                "sheet": None,
                "on_error": _choice(on_error, ("abort", "skip"), "on_error", "abort"),
            }
            if sheet:
                if not isinstance(sheet, dict):
                    raise ValueError("sheet must be an object with number")
                sh: Dict[str, Any] = {"number": _name(sheet.get("number"), "sheet.number"), "allow_foreign": bool(sheet.get("allow_foreign"))}
                if (sheet.get("x_mm") is None) != (sheet.get("y_mm") is None):
                    raise ValueError("sheet: give both x_mm and y_mm, or neither")
                if sheet.get("x_mm") is not None:
                    sh["x_mm"] = _num(sheet["x_mm"], "sheet.x_mm")
                    sh["y_mm"] = _num(sheet["y_mm"], "sheet.y_mm")
                args["sheet"] = sh
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        return self._write(tool, "make_schedule.ipy", args, workspace, approved_executor)

    def export(
        self,
        format: Any = None,  # noqa: A002 - the MCP argument is called format
        path: Any = None,
        sheets: Any = None,
        all_sheets: Any = False,
        view_ids: Any = None,
        view_id: Any = None,
        ifc_version: Any = None,
        combine: Any = True,
        overwrite: Any = False,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_export"
        try:
            fmt = _choice(format, tuple(EXPORT_EXT), "format")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("path is required")
            target = Path(path)
            if target.suffix.lower() != EXPORT_EXT[fmt]:
                raise ValueError(f"path must end in {EXPORT_EXT[fmt]} for format {fmt}")
            if not target.stem or any(c in _BAD_NAME_CHARS - {":", "\\"} for c in target.stem):
                raise ValueError("the file name has characters that are not allowed")
            target = _in_workspace(workspace, target)
            sheet_list = [_name(s, "sheets[]") for s in (sheets or [])]
            ids = _int_list(view_ids, "view_ids")
            if fmt in ("pdf", "dwg") and not (sheet_list or ids or all_sheets):
                raise ValueError(f"a {fmt} export needs sheets, all_sheets or view_ids")
            if fmt in ("pdf", "dwg") and len(sheet_list) + len(ids) > 500:
                raise ValueError("at most 500 sheets and views per export")
            args: Dict[str, Any] = {
                "format": fmt,
                "folder": str(target.parent),
                "name": target.stem,
                "ext": EXPORT_EXT[fmt][1:],
                "sheets": sheet_list,
                "all_sheets": bool(all_sheets),
                "view_ids": ids,
                "view_id": _int(view_id, "view_id") if view_id is not None else None,
                "ifc_version": _choice(ifc_version, ("IFC2x3", "IFC4", "IFC4RV", "IFC4DTV"), "ifc_version", "") or None,
                "combine": True if combine is None else bool(combine),
                "overwrite": bool(overwrite),
            }
        except _OutsideWorkspace as exc:
            return error_result(tool, "path_outside_workspace", str(exc), hint=_HINTS["path_outside_workspace"])
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        return self._write(tool, "export.ipy", args, workspace, approved_executor, export_target=target)

    # ---- shared write path -------------------------------------------------- #
    def _write(
        self,
        tool: str,
        script_name: str,
        args: Dict[str, Any],
        workspace: Any,
        approved_executor: Optional[ToolExecutor],
        export_target: Optional[Path] = None,
    ) -> Dict[str, Any]:
        parsed, elapsed, early = _run(tool, script_name, args, write=True, tool_executor=None, approved_executor=approved_executor)
        if early is not None or parsed is None:
            return early or {}
        if export_target is None:
            return _finish_write(tool, parsed, elapsed, workspace)
        return _finish_export(tool, parsed, elapsed, workspace, export_target)


class _OutsideWorkspace(ValueError):
    pass


def _in_workspace(workspace: Any, candidate: Path) -> Path:
    """Resolve a path and require it inside the workspace sandbox (the same rule the bridge applies to path arguments)."""
    if workspace is None or not getattr(workspace, "assert_in_workspace", None):
        raise _OutsideWorkspace("no workspace is configured, so no output path can be validated")
    try:
        return workspace.assert_in_workspace(Path(candidate))
    except Exception as exc:  # noqa: BLE001 - WorkspaceViolation or an OS error while resolving
        raise _OutsideWorkspace(str(exc)) from exc


def _newest_png(target: Path, since: float) -> Optional[Path]:
    """Fallback for add-in builds that do not report the real file path: the newest PNG that starts with the requested stem."""
    try:
        hits = [p for p in target.parent.glob(target.stem + "*.png") if p.is_file() and p.stat().st_mtime >= since]
    except OSError:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def _finish_export(tool: str, parsed: ScriptOutput, elapsed: int, workspace: Any, target: Path) -> Dict[str, Any]:
    """Export result: the script's file list, re-checked on the server's own disk when the file is visible there."""
    files: List[Dict[str, Any]] = []
    for r in parsed.rows:
        if r.get("row_type") != "item" or r.get("kind") != "file":
            continue
        p = Path(r.get("path", ""))
        entry: Dict[str, Any] = {"path": str(p), "bytes": int(r.get("bytes") or 0), "exists": r.get("exists") == "1", "checked_by": "addin"}
        try:
            if p.is_file():
                entry.update(bytes=p.stat().st_size, exists=True, checked_by="server")
        except OSError:
            pass
        files.append(entry)
    primary = next((f for f in files if Path(f["path"]) == target), files[0] if files else None)
    extra: Dict[str, Any] = {
        "path": primary["path"] if primary else str(target),
        "bytes": primary["bytes"] if primary else 0,
        "exists": bool(primary and primary["exists"]),
        "files": files,
    }
    result = _finish_write(tool, parsed, elapsed, workspace, extra=extra)
    disagree = [f["path"] for f in files if f["checked_by"] == "addin"]
    if files and disagree and result.get("ok"):
        result.setdefault("info", []).append("FILE_NOT_VISIBLE_TO_SERVER: size taken from the add-in because the server cannot see " + ", ".join(disagree[:3]))
    return result
