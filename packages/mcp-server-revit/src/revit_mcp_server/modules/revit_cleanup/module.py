"""
revit_cleanup module - one read-only cleanup audit of the open Revit model.

Command (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  cleanup_audit   read-only  eleven checks, each with a count, up to ``max_ids`` element ids and a severity:
                  sheets             empty sheets
                  view_templates     view templates no view and no view type default uses
                  views              views not on a sheet and not referenced (a view whose dependent view or callout is
                                     on a sheet is kept out of the candidates)
                  groups             group types with one instance, group types with none
                  levels_grids       duplicate levels and grids, levels with nothing on them, grids no dimension uses
                  rooms_areas        unplaced rooms and areas, and rooms or areas that are not enclosed or are redundant
                  cad                CAD imports and links, split into single-view and model-wide
                  warnings           the document's warnings by type (top 10)
                  detail_lines       detail lines drawn in model views (views with the most are listed)
                  families           loadable families and types with no instance; in-place families listed separately
                  duplicates         same-category elements at the same place or overlapping (bounded)

How it runs: the same seam as ``revit_params``. The command builds one IronPython 2.7 script from the revit module's
``_prelude.ipy`` and ``_helpers.ipy`` plus ``scripts/cleanup_audit.ipy``, injects the arguments as an ``ARGS`` literal and
sends it with ``mode: "read"``. The server validates that script (``security/read_mode.py``): it contains no
Transaction, no file, process or network access. The printed line protocol becomes the plan section 6 contract.

Scope (the ``scope`` argument):
  * ``{"mode": "model"}`` (default): the whole model, all checks, bounded by ``time_budget_s`` and ``max_elements``. A
    check that runs out of budget reports ``truncated``; it never reports a result it could not finish.
  * ``{"mode": "categories", "categories": [...]}``: element-level checks for those categories only (families,
    duplicates, rooms and areas when they are included, warnings that involve those elements). Document-level checks
    (sheets, view templates, views, levels and grids, groups, CAD, detail lines) are listed as ``skipped``.
  * ``{"mode": "view", "view_id": n}``: element-level checks for what is visible in that view (CAD, rooms and areas,
    detail lines, duplicates, warnings). Families and document-level checks are ``skipped``.

Verdict (plan section 6): FAIL when a finding has severity FAIL; else INCOMPLETE when any check was truncated, partial,
unreadable or not run, or nothing ran; else WARN when there are WARN findings; else PASS. A truncated or unreadable
check can never give PASS.

``purge_candidates`` (a separate field, see module.json): element ids that a LATER, separately approved tool could act
on. This tool deletes nothing and has no way to. The lists are candidates with the rule that produced them
(``basis``), not a statement that deleting them is safe: they say "unplaced" or "unused" by one measured rule, and the
rules cannot see everything (see UNVERIFIED). In-place families, levels, grids, groups with one instance and
anything the audit could not read are never candidates.

UNVERIFIED: nothing here has run against a live Revit. The script is exercised against a small stub of the Revit API
(tests/revit_cleanup_stub.py). Specifically unproven in a live model: Element.GetDependentElements(ElementClassFilter)
and View.GetDependentViewIds() for dependent views and callouts, ViewSheet.GetAllPlacedViews() including schedules,
ViewSheet.IsPlaceholder, ViewFamilyType.DefaultTemplateId, ImportInstance.IsLinked / OwnerViewId, Group.GroupType,
ElementLevelFilter on a level with only view-based content, Room.Location / Area for unplaced and not enclosed rooms,
CurveElement.CurveElementType == DetailCurve, Family.IsInPlace, the categories that are skipped for family types, the
run time on a large model (the time budget and caps are the guard), and the heuristics for duplicates.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from revit_mcp_server.check_contract import (
    ScriptOutput,
    cast_rows,
    error_result,
    mock_result,
    parse_script_output,
)

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
REVIT_SCRIPT_DIR = MODULE_DIR.parent / "revit" / "scripts"
PRELUDE = REVIT_SCRIPT_DIR / "_prelude.ipy"
HELPERS = REVIT_SCRIPT_DIR / "_helpers.ipy"
SCRIPT = "cleanup_audit.ipy"
EXECUTE_TOOL = "revit_execute_python"
TOOL = "revit_cleanup_audit"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

CHECKS = (
    "sheets", "view_templates", "views", "groups", "levels_grids", "rooms_areas", "cad", "warnings",
    "detail_lines", "families", "duplicates",
)
SCOPE_MODES = ("model", "categories", "view")
INCOMPLETE = ("truncated", "partial", "unreadable", "not_run")
SEVERITIES = ("FAIL", "WARN", "INFO")
_CATEGORY = re.compile(r"^[A-Za-z0-9_ ]{1,60}$")

PURGE_NOTE = (
    "Candidates for a later, separately approved tool. This audit changed and deleted nothing. A candidate is 'unplaced' "
    "or 'unused' by the one rule named in basis; it is not a statement that removing it is safe."
)

_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "script_exception": "The embedded script failed inside Revit. It is read-only, so the model was not changed.",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id.",
}

ROW_TYPES = {
    "count": "int", "id_total": "int", "ids": "intlist", "elapsed_ms": "int", "view_id": "int",
}


# --------------------------------------------------------------------------- #
# Script building and the seam to Revit
# --------------------------------------------------------------------------- #
def build_script(args: Dict[str, Any]) -> str:
    """Prelude + helpers + ``ARGS`` literal + the audit script. Arguments are validated ASCII, so ``ascii()`` is safe."""
    parts = [PRELUDE.read_text(encoding="utf-8"), HELPERS.read_text(encoding="utf-8"), f"ARGS = {ascii(args)}"]
    parts.append((SCRIPT_DIR / SCRIPT).read_text(encoding="utf-8"))
    return "\n\n".join(parts) + "\n"


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


def _bridge_failure(exc: Exception) -> Dict[str, Any]:
    text = str(exc)
    low = text.lower()
    if "timed out" in low or "timeout" in low:
        return error_result(TOOL, "timeout_running", text, hint=_HINTS["timeout_running"])
    return error_result(
        TOOL, "bridge_error", text,
        hint="Check that Revit is running with the AEC Model Bridge add-in and a project open (revit_health).",
    )


# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #
def _number(value: Any, what: str, default: float, low: float, high: float, whole: bool = False) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or abs(value) == float("inf"):
        raise ValueError(f"{what} must be a number")
    if whole and int(value) != value:
        raise ValueError(f"{what} must be a whole number")
    if not low <= value <= high:
        raise ValueError(f"{what} must be between {low:g} and {high:g}")
    return int(value) if whole else float(value)


def clean_scope(scope: Any) -> Dict[str, Any]:
    """Validated scope: {mode: model} | {mode: categories, categories: [...]} | {mode: view, view_id: n}."""
    if scope in (None, {}):
        return {"mode": "model"}
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    extra = set(scope) - {"mode", "categories", "view_id"}
    if extra:
        raise ValueError(f"scope has unknown keys: {', '.join(sorted(extra))}")
    mode = scope.get("mode") or "model"
    if mode not in SCOPE_MODES:
        raise ValueError(f"scope.mode must be one of {', '.join(SCOPE_MODES)}")
    if mode == "model":
        if scope.get("categories") or scope.get("view_id") is not None:
            raise ValueError("scope.mode 'model' takes no categories or view_id")
        return {"mode": "model"}
    if mode == "categories":
        cats = scope.get("categories")
        if not isinstance(cats, list) or not 1 <= len(cats) <= 30:
            raise ValueError("scope.categories must be a list of 1 to 30 category names for mode 'categories'")
        out = []
        for c in cats:
            if not isinstance(c, str) or not _CATEGORY.match(c.strip()):
                raise ValueError("scope.categories entries must be category names such as Walls, Doors or OST_GenericModel")
            out.append(c.strip())
        if scope.get("view_id") is not None:
            raise ValueError("scope.mode 'categories' takes no view_id")
        return {"mode": "categories", "categories": out}
    view_id = scope.get("view_id")
    if isinstance(view_id, bool) or not isinstance(view_id, int) or view_id <= 0:
        raise ValueError("scope.view_id must be the integer ElementId of a view for mode 'view'")
    if scope.get("categories"):
        raise ValueError("scope.mode 'view' takes no categories")
    return {"mode": "view", "view_id": view_id}


def clean_args(
    scope: Any, checks: Any, max_ids: Any, max_purge_ids: Any, time_budget_s: Any, max_elements: Any,
    tolerance_mm: Any, overlap_ratio: Any, detail_line_warn: Any,
) -> Dict[str, Any]:
    if checks is None:
        wanted = list(CHECKS)
    else:
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"checks must be a non-empty list drawn from: {', '.join(CHECKS)}")
        unknown = [c for c in checks if c not in CHECKS]
        if unknown:
            raise ValueError(f"unknown check(s) {unknown}; choose from {', '.join(CHECKS)}")
        wanted = [c for c in CHECKS if c in checks]
    return {
        "scope": clean_scope(scope),
        "checks": wanted,
        "max_ids": int(_number(max_ids, "max_ids", 20, 1, 200, True)),
        "max_purge_ids": int(_number(max_purge_ids, "max_purge_ids", 200, 1, 2000, True)),
        "time_budget_s": _number(time_budget_s, "time_budget_s", 20.0, 1.0, 25.0),
        "max_elements": int(_number(max_elements, "max_elements", 150000, 1000, 500000, True)),
        "tolerance_mm": _number(tolerance_mm, "tolerance_mm", 5.0, 0.1, 500.0),
        "overlap_ratio": _number(overlap_ratio, "overlap_ratio", 0.9, 0.5, 1.0),
        "detail_line_warn": int(_number(detail_line_warn, "detail_line_warn", 500, 1, 1000000, True)),
    }


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #
def verdict_of(checks: List[Dict[str, Any]], findings: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """(FAIL | INCOMPLETE | WARN | PASS, names of the checks that did not finish). Never PASS on an unfinished check."""
    unfinished = [str(c["check"]) for c in checks if c["status"] in INCOMPLETE]
    ran = [c for c in checks if c["status"] == "ran"]
    if any(f["severity"] == "FAIL" for f in findings):
        return "FAIL", unfinished
    if unfinished or not ran:
        return "INCOMPLETE", unfinished
    if any(f["severity"] == "WARN" for f in findings):
        return "WARN", unfinished
    return "PASS", unfinished


def _line(f: Dict[str, Any]) -> str:
    shown = len(f["element_ids"])
    ids = ",".join(str(i) for i in f["element_ids"])
    more = f" (+{f['id_total'] - shown} more)" if f["id_total"] > shown else ""
    tail = f"; ids {ids}{more}" if ids else ""
    return f"{f['code']} ({f['count']}): {f['note']}{tail}"


def _split_names(text: str) -> List[str]:
    return [p.strip() for p in text.split(" | ") if p.strip()]


def scope_text(scope: Dict[str, Any]) -> str:
    if scope["mode"] == "categories":
        return "categories " + ", ".join(scope["categories"])
    if scope["mode"] == "view":
        return f"view {scope['view_id']}"
    return "the whole model"


def build_result(parsed: ScriptOutput, args: Dict[str, Any], elapsed_ms: int) -> Dict[str, Any]:
    """Section 6 contract from the printed rows."""
    rows = cast_rows(parsed.rows, ROW_TYPES)
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_kind.setdefault(str(r.get("kind")), []).append(r)

    checks = [
        {"check": r.get("check"), "status": r.get("status"), "elapsed_ms": r.get("elapsed_ms") or 0, "note": r.get("note", "")}
        for r in by_kind.get("check", [])
    ]
    seen = {c["check"] for c in checks}
    for name in args["checks"]:
        if name not in seen:
            checks.append({"check": name, "status": "not_run", "elapsed_ms": 0, "note": "the script returned no result for this check"})
    order = {name: i for i, name in enumerate(CHECKS)}
    checks.sort(key=lambda c: order.get(str(c["check"]), 99))

    findings = []
    for r in by_kind.get("finding", []):
        ids = r.get("ids") or []
        findings.append({
            "check": r.get("check"), "code": r.get("code"), "severity": r.get("severity") if r.get("severity") in SEVERITIES else "INFO",
            "count": r.get("count") or 0, "id_total": r.get("id_total") or len(ids), "element_ids": ids,
            "names": _split_names(str(r.get("names", ""))), "note": r.get("note", ""),
        })
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (rank[f["severity"]], order.get(str(f["check"]), 99), str(f["code"])))

    groups: Dict[str, Any] = {}
    for r in by_kind.get("purge", []):
        ids = r.get("ids") or []
        total = r.get("count") or len(ids)
        groups[str(r.get("group"))] = {"count": total, "element_ids": ids, "truncated": total > len(ids), "basis": r.get("basis", "")}
    purge_total = sum(g["count"] for g in groups.values())

    verdict, unfinished = verdict_of(checks, findings)
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    skipped = [c for c in checks if c["status"] == "skipped"]
    ran = [c for c in checks if c["status"] == "ran"]
    text = f"{verdict}: {counts['FAIL']} FAIL, {counts['WARN']} WARN, {counts['INFO']} INFO for {scope_text(args['scope'])}; {len(ran)} of {len(checks) - len(skipped)} checks complete"
    if unfinished:
        text += " (not finished: " + ", ".join(unfinished) + ")"
    if skipped:
        text += f"; {len(skipped)} outside this scope"
    if purge_total:
        text += f". {purge_total} purge candidate ids in {len(groups)} groups (candidates only, nothing was changed)"

    info = [_line(f) for f in findings if f["severity"] == "INFO"]
    info += [f"{c['check']} {c['status']}: {c['note']}" for c in skipped]
    info += [f"{c['check']} {c['status']}: {c['note']}" for c in checks if c["status"] in INCOMPLETE]
    info += parsed.infos
    truncated = any(c["status"] in ("truncated", "not_run") for c in checks)
    partial = any(c["status"] in ("partial", "unreadable") for c in checks) or parsed.meta.get("partial") in ("1", "true")
    complete = bool(ran) and not unfinished

    return {
        "ok": True,
        "tool": TOOL,
        "read_only": True,
        "verdict": verdict,
        "verified": complete,
        "build": None,
        "document": {"title": parsed.meta.get("doc_title"), "guid": parsed.meta.get("doc_guid")},
        "revit_version": parsed.meta.get("revit_version"),
        "elapsed_ms": int(elapsed_ms),
        "summary": text,
        "scope": args["scope"],
        "fails": [_line(f) for f in findings if f["severity"] == "FAIL"],
        "warns": [_line(f) for f in findings if f["severity"] == "WARN"],
        "info": info,
        "findings": findings,
        "checks": checks,
        "warnings_by_type": [
            {"count": r.get("count"), "description": r.get("description", ""), "element_ids": r.get("ids") or []}
            for r in by_kind.get("warning_type", [])
        ],
        "detail_line_views": [
            {"view_id": r.get("view_id"), "name": r.get("name", ""), "view_type": r.get("view_type", ""), "count": r.get("count")}
            for r in by_kind.get("detail_line_view", [])
        ],
        "purge_candidates": {"note": PURGE_NOTE, "total_ids": purge_total, "groups": groups},
        "changed_ids": [],
        "detail_file": None,
        "counts": {"fails": counts["FAIL"], "warns": counts["WARN"], "info": counts["INFO"]},
        "limits": {
            "truncated": truncated,
            "partial": partial,
            "max_ids": args["max_ids"],
            "max_purge_ids": args["max_purge_ids"],
            "ids_capped": any(f["id_total"] > len(f["element_ids"]) for f in findings) or any(g["truncated"] for g in groups.values()),
            "time_budget_s": args["time_budget_s"],
            "max_elements": args["max_elements"],
        },
        "truncated": truncated or partial,
    }


def _mock() -> Dict[str, Any]:
    result = mock_result(TOOL)
    result.update(verdict="INCOMPLETE", verified=False, read_only=True, warns=[], findings=[], checks=[])
    result["purge_candidates"] = {"note": PURGE_NOTE, "total_ids": 0, "groups": {}}
    return result


def _running(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tool": TOOL,
        "status": "running",
        "request_id": raw.get("request_id"),
        "verified": False,
        "verdict": "INCOMPLETE",
        "summary": "Revit is still working on this request; the outcome is not known yet.",
        "message": raw.get("message") or "Call revit_get_result with this request_id to collect the output.",
        "hint": _HINTS["timeout_running"],
        "changed_ids": [],
    }


class RevitCleanupModule:
    def cleanup_audit(
        self,
        scope: Any = None,
        checks: Any = None,
        max_ids: Any = None,
        max_purge_ids: Any = None,
        time_budget_s: Any = None,
        max_elements: Any = None,
        tolerance_mm: Any = None,
        overlap_ratio: Any = None,
        detail_line_warn: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            args = clean_args(scope, checks, max_ids, max_purge_ids, time_budget_s, max_elements, tolerance_mm, overlap_ratio, detail_line_warn)
        except (TypeError, ValueError) as exc:
            return error_result(TOOL, "invalid_input", str(exc), hint=_HINTS["invalid_input"])
        if _server_in_mock_mode():
            return _mock()
        if tool_executor is None:
            return error_result(
                TOOL, "no_bridge", "No connection to the Revit tools in this session.",
                hint="This tool must run inside the AEC Model Bridge server (module provider with a tool registry).",
            )
        script = build_script(args)
        started = time.perf_counter()
        try:
            raw = tool_executor(EXECUTE_TOOL, {"script": script, "mode": "read"})
        except Exception as exc:  # noqa: BLE001 - classified into a structured error
            return _bridge_failure(exc)
        elapsed = int((time.perf_counter() - started) * 1000)
        if _is_mock(raw):
            return _mock()
        if _is_running(raw):
            return _running(raw)
        text, err = _script_text(raw)
        if text is None:
            return error_result(TOOL, "script_error", err, hint="The add-in reported a script error before any result was produced. Read-only: the model is unchanged.")
        parsed = parse_script_output(text)
        if parsed.errors:
            kind, message = parsed.errors[0]
            return error_result(TOOL, kind, message, hint=_HINTS.get(kind, ""))
        if not any(r.get("kind") == "check" for r in parsed.rows):
            return error_result(
                TOOL, "unparsable_output",
                f"The script printed no check results (ignored {parsed.ignored_lines} lines).",
                hint="The add-in may run an older or different IronPython engine; call revit_get_context and report the build.",
            )
        return build_result(parsed, args, elapsed)
