"""
sheet_view_audit module - read-only sheet and view checks over a saved snapshot.

Command:
  run_audit - empty sheets, views not on any sheet, duplicate sheet numbers,
              sheets missing required parameters, default view names, and
              sheet counts per discipline prefix.

Snapshot data. Two sources are understood:

1. What the Revit add-in writes today: ordinary `elements` records. Sheets are
   records of class "ViewSheet" (number/name in params "Sheet Number" and
   "Sheet Name"); drafting views are class "ViewDrafting". There is NO record of
   which views sit on which sheet, and model views (plans, sections, 3D) are not
   extracted. From this the audit can only run: duplicate sheet numbers, missing
   sheet parameters, and default names on drafting views. The other checks
   report "not_enough_data" and the overall status is "partial".
2. Optional top-level lists (not written by the add-in yet), which enable every check:

  "sheets": [{"uid", "number", "name", "view_uids": [...], "params": {name: value}}]
  "views":  [{"uid", "name", "view_type", "is_template", "sheet_uid", "discipline"}]

When there is no sheet data at all the audit says so instead of guessing.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

DEFAULT_REQUIRED = ["Sheet Number", "Sheet Name"]

# View types that Revit never places on a sheet.
_UNPLACEABLE_TYPES = {"projectbrowser", "systembrowser", "internal", "undefined", "revisionschedule"}

_DEFAULT_NAME_PATTERNS = [
    (re.compile(r"^\s*copy of\b", re.I), "starts with 'Copy of'"),
    (re.compile(r"\bcopy\s*\d*\s*$", re.I), "ends with 'Copy'"),
    (re.compile(r"^\s*\{3D[^}]*\}\s*$", re.I), "is the default '{3D}' name"),
    (re.compile(r"^\s*(section|detail|callout|elevation|drafting view)\s+\d+\s*$", re.I), "is a Revit default name"),
]

_SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


def _finding(check: str, severity: str, message: str, uids: List[Any], next_step: str) -> Dict[str, Any]:
    return {
        "check": check,
        "severity": severity,
        "message": message,
        "unique_ids": sorted({u for u in uids if u}),
        "next_step": next_step,
    }


def _sheet_value(sheet: Dict[str, Any], param: str) -> Any:
    key = param.strip().lower()
    if key in ("sheet number", "number"):
        return sheet.get("number")
    if key in ("sheet name", "name"):
        return sheet.get("name")
    for k, v in (sheet.get("params") or {}).items():
        if k.strip().lower() == key:
            return v.get("v") if isinstance(v, dict) else v
    return None


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _prefix(number: Any) -> str:
    m = re.match(r"^\s*([A-Za-z]+)", str(number or ""))
    return m.group(1).upper() if m else "(none)"


def _default_name_reason(name: str) -> str:
    for pattern, reason in _DEFAULT_NAME_PATTERNS:
        if pattern.search(name or ""):
            return reason
    return ""


def _preview(names: List[str], limit: int = 5) -> str:
    text = ", ".join(names[:limit])
    return text + ("..." if len(names) > limit else "")


ALL_CHECKS = (
    "empty_sheets", "views_not_on_sheet", "duplicate_sheet_numbers",
    "missing_sheet_parameter", "default_view_names",
)


def _param(rec: Dict[str, Any], *names: str) -> Any:
    params = rec.get("params") or {}
    for n in names:
        v = params.get(n)
        if isinstance(v, dict):
            v = v.get("v")
        if not _is_blank(v):
            return v
    return None


def derive_from_elements(elements: List[Dict[str, Any]]):
    """Build sheet and drafting-view records from a live snapshot's elements."""
    sheets: List[Dict[str, Any]] = []
    views: List[Dict[str, Any]] = []
    for el in elements:
        cls = el.get("class") or el.get("cls")
        if cls == "ViewSheet":
            sheets.append({
                "uid": el.get("uid"), "number": _param(el, "Sheet Number"),
                "name": _param(el, "Sheet Name"), "params": el.get("params") or {},
            })
        elif cls == "ViewDrafting":
            views.append({
                "uid": el.get("uid"), "name": _param(el, "View Name", "Name") or "",
                "view_type": "DraftingView",
            })
    return sheets, views


def audit_sheets_and_views(
    sheets: List[Dict[str, Any]],
    views: List[Dict[str, Any]],
    required_params: List[str],
    checks: Optional[Any] = None,
) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    enabled = set(ALL_CHECKS if checks is None else checks)

    placed = set()
    for s in sheets:
        placed.update(s.get("view_uids") or [])
    for v in views:
        if v.get("sheet_uid"):
            placed.add(v.get("uid"))

    # 1. Empty sheets
    empty = [] if "empty_sheets" not in enabled else [
        s for s in sheets
        if not (s.get("view_uids") or [])
        and not any(v.get("sheet_uid") == s.get("uid") for v in views)
    ]
    if empty:
        findings.append(_finding(
            "empty_sheets", "warning",
            f"{len(empty)} sheet(s) have no views on them: "
            + _preview([f"{s.get('number', '?')} {s.get('name', '')}".strip() for s in empty]),
            [s.get("uid") for s in empty],
            "Place a view on each of these sheets, or delete the sheets if they are not needed.",
        ))

    # 2. Views not on any sheet
    unplaced = [] if "views_not_on_sheet" not in enabled else [
        v for v in views
        if not v.get("is_template")
        and str(v.get("view_type", "")).replace(" ", "").lower() not in _UNPLACEABLE_TYPES
        and v.get("uid") not in placed
    ]
    if unplaced:
        findings.append(_finding(
            "views_not_on_sheet", "info",
            f"{len(unplaced)} view(s) are not placed on any sheet: "
            + _preview([str(v.get("name", "?")) for v in unplaced]),
            [v.get("uid") for v in unplaced],
            "Put each view on a sheet if it should be issued, or delete it if it is a leftover working view.",
        ))

    # 3. Duplicate sheet numbers
    by_number: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in sheets:
        num = str(s.get("number") or "").strip()
        if num:
            by_number[num.lower()].append(s)
    dupes = [] if "duplicate_sheet_numbers" not in enabled else [group for group in by_number.values() if len(group) > 1]
    if dupes:
        findings.append(_finding(
            "duplicate_sheet_numbers", "error",
            f"{len(dupes)} sheet number(s) are used more than once: "
            + _preview([str(group[0].get("number")) for group in dupes]),
            [s.get("uid") for group in dupes for s in group],
            "Renumber the duplicate sheets so every sheet number is unique.",
        ))

    # 4. Missing required parameters
    for param in required_params if "missing_sheet_parameter" in enabled else []:
        missing = [s for s in sheets if _is_blank(_sheet_value(s, param))]
        if missing:
            findings.append(_finding(
                "missing_sheet_parameter", "warning",
                f"{len(missing)} sheet(s) have an empty '{param}'.",
                [s.get("uid") for s in missing],
                f"Fill in '{param}' on these sheets.",
            ))

    # 5. Default view names
    bad = [] if "default_view_names" not in enabled else [
        v for v in views if not v.get("is_template") and _default_name_reason(str(v.get("name", "")))
    ]
    if bad:
        findings.append(_finding(
            "default_view_names", "info",
            f"{len(bad)} view(s) still have a default or copied name: "
            + _preview([f"'{v.get('name')}'" for v in bad]),
            [v.get("uid") for v in bad],
            "Rename these views to match your office view naming standard.",
        ))

    findings.sort(key=lambda f: _SEV_ORDER[f["severity"]])

    counts: Dict[str, int] = defaultdict(int)
    for s in sheets:
        counts[_prefix(s.get("number"))] += 1
    view_discipline: Dict[str, int] = defaultdict(int)
    for v in views:
        if v.get("discipline"):
            view_discipline[str(v["discipline"])] += 1

    return {
        "status": "ok",
        "sheet_count": len(sheets),
        "view_count": len(views),
        "sheets_per_discipline_prefix": dict(sorted(counts.items())),
        "views_per_discipline": dict(sorted(view_discipline.items())),
        "total_findings": len(findings),
        "by_severity": {sev: sum(1 for f in findings if f["severity"] == sev) for sev in _SEV_ORDER},
        "findings": findings,
    }


class SheetViewAuditModule:

    def run_audit(
        self,
        snapshot_id: str = "",
        required_sheet_parameters: Optional[List[str]] = None,
        workspace: Any = None,
        **_,
    ) -> Dict[str, Any]:
        if not snapshot_id:
            raise ValueError("sheet_view_audit_run_audit needs a snapshot_id. Take a snapshot first and pass its id.")
        path = workspace.allowed_directories[0] / "snapshots" / f"{snapshot_id}.json"
        if not path.exists():
            raise ValueError(f"Snapshot '{snapshot_id}' not found.")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        explicit = "sheets" in data or "views" in data
        if explicit:
            sheets = data.get("sheets") or []
            views = data.get("views") or []
            source = "top-level sheets/views lists"
        else:
            sheets, views = derive_from_elements(data.get("elements") or [])
            source = "ViewSheet / ViewDrafting element records"
        if not sheets and not views:
            return {
                "status": "no_sheet_view_data",
                "message": (
                    "This snapshot has no sheets or views in it, so nothing was checked "
                    "(not even 'no problems found'). Take a snapshot of a project that has sheets."
                ),
                "total_findings": 0,
                "findings": [],
            }

        placement_known = bool(sheets) and all("view_uids" in s for s in sheets) if explicit else False
        have_views_list = explicit and "views" in data
        checks = {
            "duplicate_sheet_numbers": (bool(sheets), "No sheets were found in the snapshot.", ["sheet records"]),
            "missing_sheet_parameter": (bool(sheets), "No sheets were found in the snapshot.", ["sheet records"]),
            "empty_sheets": (
                placement_known and bool(sheets),
                "The snapshot does not say which views are placed on which sheet, so empty sheets cannot be told apart.",
                ["which views are on each sheet (view_uids per sheet)"],
            ),
            "views_not_on_sheet": (
                placement_known and have_views_list,
                "The snapshot has no full list of views and no record of which are placed on sheets "
                "(only sheets and drafting views are extracted), so unplaced views cannot be found.",
                ["all views (plans, sections, 3D, schedules)", "which views are on each sheet"],
            ),
            "default_view_names": (
                bool(views),
                "The snapshot has no views, so view names cannot be checked.",
                ["view records"],
            ),
        }
        enabled = [k for k, (ok, _, _) in checks.items() if ok]
        report = {
            k: ({"status": "ran"} if ok else {"status": "not_enough_data", "reason": why, "missing": miss})
            for k, (ok, why, miss) in checks.items()
        }
        if "default_view_names" in enabled and not have_views_list:
            report["default_view_names"]["note"] = "Only drafting views were in the snapshot; other views were not checked."

        required = DEFAULT_REQUIRED if required_sheet_parameters is None else list(required_sheet_parameters)
        result = audit_sheets_and_views(sheets, views, required, enabled)
        skipped = [k for k in report if report[k]["status"] != "ran"]
        if skipped:
            result["status"] = "partial"
            result["message"] = (
                "Not enough data in this snapshot for: " + ", ".join(skipped)
                + ". Those checks were NOT run, so zero findings for them does not mean they are fine. "
                + "Details are under 'checks'."
            )
        result["checks"] = report
        result["data_source"] = source
        result["snapshot_id"] = snapshot_id
        result["required_sheet_parameters"] = required
        return result
