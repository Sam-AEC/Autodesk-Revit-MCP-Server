"""
revit module - read-only "eyes" for an AI working in a live Revit session (Phase 1 of
docs/upgrade-plan-hands-and-eyes.md).

Commands (tool names are ``revit_<command>``):
  check_joins         1.2  per wall end: joined or not, to which walls, join type
  check_intersections 1.3  solid/solid overlap volumes (BooleanOperationsUtils); mode=bbox kept
  warnings_delta      1.8  snapshot a warnings baseline, later list new / closed warnings
  check_orientation   1.9  probe 0.6 m along each exterior wall's Orientation, flag walls facing into a room
  audit_openings      1.4  doors and windows: host, centre in the wall piece, cut (ray / volume), sill / head, swing vs hinge
  audit_roofs         1.5  roofs: top vs level, slope, footprint coverage, open edges without parapet, stair openings
  probe_family        1.6  nested instances, category, parameters, connectors, geometry extents and sill datum of a family
  system_report       1.7  piping / duct systems: open ends, disconnected fittings, unconnected ports, flow and size mismatches
  review              4.5  one call: runs the audits above plus the warnings delta; FAIL lines and what could not be verified
  check_naming_and_params   required parameters empty or missing, duplicate marks, names off a pattern
  check_levels_grids        levels without a plan view, duplicate elevations, grids on top of each other

How it works: each command is thin. It builds an IronPython 2.7 script from ``scripts/_prelude.ipy`` plus one
tool script, injects the arguments as an ``ARGS`` literal, runs it inside Revit and turns the printed line
protocol into the contract of plan section 6 (``revit_mcp_server.check_contract``): summary, FAIL lines, INFO
lines, pageable rows, and a detail file in the workspace when lists are long. The scripts never open a
transaction. Output is capped (default 50 rows; limit / offset / count_only / fields).

The seam: ``run_readonly_script`` is the ONLY place that sends the script to Revit. It uses
``revit_execute_python`` with ``mode: "read"``; the server and add-in both validate that script before execution.
These checks describe the selected elements and available geometry, not engineering calculations. Missing
geometry, inaccessible family documents and bounded partial results are reported as unverified.

Everything that needs a running Revit with the add-in is UNVERIFIED here: the scripts are syntax-checked and
exercised against a stub of the Revit API in the tests, not against Revit.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from revit_mcp_server.check_contract import (
    PageSpec,
    ScriptOutput,
    assemble_result,
    error_result,
    is_safe_name,
    load_json,
    mock_result,
    new_baseline_id,
    parse_script_output,
    save_json,
    write_detail_file,
)

SCRIPT_DIR = Path(__file__).resolve().parent / "scripts"
PRELUDE = "_prelude.ipy"
HELPERS = "_helpers.ipy"
# The first four tool scripts are self-contained; the newer ones share the helpers file.
HELPER_SCRIPTS = frozenset(
    {
        "audit_openings.ipy",
        "audit_roofs.ipy",
        "probe_family.ipy",
        "system_report.ipy",
        "check_naming_and_params.ipy",
        "check_levels_grids.ipy",
    }
)
EXECUTE_TOOL = "revit_execute_python"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

# The checks revit_review can run, in the order it runs them (cheap and decisive first).
REVIEW_CHECKS = ("levels_grids", "joins", "orientation", "openings", "roofs", "naming_params", "systems", "intersections", "warnings")

_HINTS = {
    "invalid_input": "Give ids, a tag (a prefix of the Comments parameter) or categories; every tool needs an explicit scope.",
    "too_many_elements": "Narrow the selection with ids or a more specific tag, or raise max_elements.",
    "empty_selection": "Check the spelling: tag must be a prefix of the Comments parameter of the elements you built.",
    "script_exception": "The embedded script failed inside Revit. It is read-only, so the model was not changed.",
}


# --------------------------------------------------------------------------- #
# Script building and the seam to Revit
# --------------------------------------------------------------------------- #
def build_script(script_name: str, args: Dict[str, Any]) -> str:
    """Prelude + ``ARGS`` literal + tool script. ``ascii(repr)`` output is valid IronPython 2.7 source."""
    prelude = (SCRIPT_DIR / PRELUDE).read_text(encoding="utf-8")
    if script_name in HELPER_SCRIPTS:
        prelude += "\n\n" + (SCRIPT_DIR / HELPERS).read_text(encoding="utf-8")
    body = (SCRIPT_DIR / script_name).read_text(encoding="utf-8")
    return f"{prelude}\n\nARGS = {ascii(args)}\n\n{body}\n"


def run_readonly_script(script: str, tool_executor: ToolExecutor) -> Any:
    """Send a read-only IronPython script to Revit and return the bridge's raw answer.

    The shared dispatcher validates the generated script before skipping approval for mode "read".
    """
    return tool_executor(EXECUTE_TOOL, {"script": script, "mode": "read"})


def _server_in_mock_mode() -> bool:
    """True when the server runs with MCP_REVIT_MODE=mock (no Revit): nothing can be measured."""
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


def _script_text(raw: Any) -> Tuple[Optional[str], str]:
    """Unwrap the add-in answer to ``(stdout text or None, error text)``."""
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
        return error_result(
            tool,
            "approval_required",
            text,
            hint=(
                "revit_execute_python is still gated as a write tool in this build, so the read-only check scripts "
                "cannot run without an approved plan. They run ungated once execute_python supports mode 'read' "
                "(upgrade plan item 0.6). Nothing was sent to Revit."
            ),
        )
    if "timed out" in low or "timeout" in low:
        return error_result(
            tool,
            "timeout_running",
            text,
            hint=(
                "The bridge waits 30 s; Revit may still be running the script. Call revit_health until it answers "
                "before anything else, then narrow the sets (tag/ids) or lower time_budget_s and run again."
            ),
        )
    return error_result(
        tool,
        "bridge_error",
        text,
        hint="Check that Revit is running with the AEC Model Bridge add-in and a project open (revit_health).",
    )


def _execute(
    tool: str,
    script_name: str,
    script_args: Dict[str, Any],
    tool_executor: Optional[ToolExecutor],
) -> Tuple[Optional[ScriptOutput], int, Optional[Dict[str, Any]]]:
    """Run one script. Returns ``(parsed, elapsed_ms, early_result)``; ``early_result`` is an error/mock contract."""
    if _server_in_mock_mode():
        return None, 0, mock_result(tool)
    if tool_executor is None:
        return None, 0, error_result(
            tool,
            "no_bridge",
            "No connection to the Revit tools in this session.",
            hint="This tool must run inside the AEC Model Bridge server (module provider with a tool registry).",
        )
    script = build_script(script_name, script_args)
    started = time.perf_counter()
    try:
        raw = run_readonly_script(script, tool_executor)
    except Exception as exc:  # noqa: BLE001 - classified into a structured error
        return None, 0, _bridge_failure(tool, exc)
    elapsed = int((time.perf_counter() - started) * 1000)
    if _is_mock(raw):
        return None, elapsed, mock_result(tool)
    text, err = _script_text(raw)
    if text is None:
        return None, elapsed, error_result(
            tool, "script_error", err, hint="The add-in reported a script error before any result was produced. Read-only: the model is unchanged."
        )
    parsed = parse_script_output(text)
    if parsed.errors:
        kind, message = parsed.errors[0]
        return None, elapsed, error_result(tool, kind, message, hint=_HINTS.get(kind, ""))
    if not parsed.summary and not parsed.counts:
        return None, elapsed, error_result(
            tool,
            "unparsable_output",
            "The script printed no summary and no counts (ignored %d lines)." % parsed.ignored_lines,
            hint="The add-in may be running an older or different IronPython engine; call revit_health and report the build.",
        )
    return parsed, elapsed, None


# --------------------------------------------------------------------------- #
# Argument helpers
# --------------------------------------------------------------------------- #
_TAG = re.compile(r"^[ -~]{1,80}$")  # printable ASCII only: it becomes a literal inside the script


def _int_list(value: Any) -> List[int]:
    out: List[int] = []
    for v in value or []:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
            raise ValueError(f"element ids must be integers, got {v!r}")
        out.append(int(v))
    return out


def _tag(value: Any) -> str:
    tag = str(value or "")
    if tag and not _TAG.match(tag):
        raise ValueError("tag must be 1-80 printable ASCII characters")
    return tag


def _selection(ids: Any, tag: Any, categories: Any) -> Dict[str, Any]:
    return {
        "ids": _int_list(ids),
        "tag": _tag(tag),
        "categories": [str(c) for c in (categories or [])],
    }


def _clean_data(value: Any, depth: int = 0) -> Any:
    """Plain, literal-safe copy of caller data: dicts, lists, finite numbers, bools, printable ASCII strings."""
    if depth > 5:
        raise ValueError("data is nested too deeply")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("data holds a number that is not finite")
        return float(value)
    if isinstance(value, str):
        if not _TAG.match(value):
            raise ValueError("data strings must be 1-80 printable ASCII characters")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 2000:
            raise ValueError("data has a list with more than 2000 entries")
        return [_clean_data(v, depth + 1) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str) or not re.match(r"^[A-Za-z0-9_]{1,40}$", k):
                raise ValueError("data keys must be plain names (letters, digits, underscore)")
            out[k] = _clean_data(v, depth + 1)
        return out
    raise ValueError(f"data cannot hold a {type(value).__name__}")


def _names(value: Any, what: str) -> List[str]:
    out: List[str] = []
    for v in value or []:
        text = str(v)
        if not _TAG.match(text):
            raise ValueError(f"{what} must be 1-80 printable ASCII characters")
        out.append(text)
    return out


def _budget(value: Any, default: float) -> float:
    """Script time budget in seconds, 1..25 (the bridge itself waits 30 s)."""
    return max(1.0, min(float(value if value is not None else default), 25.0))


def _bad_input(tool: str, exc: Exception) -> Dict[str, Any]:
    return error_result(tool, "invalid_input", str(exc), hint=_HINTS["invalid_input"])


def _finish(tool: str, parsed: ScriptOutput, elapsed: int, page: PageSpec, workspace: Any, **kw: Any) -> Dict[str, Any]:
    return assemble_result(tool, parsed, page, elapsed_ms=elapsed, workspace=workspace, **kw)


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
class RevitModule:

    def check_joins(
        self,
        ids: Optional[List[int]] = None,
        tag: str = "",
        categories: Optional[List[str]] = None,
        allow_free_ids: Optional[List[int]] = None,
        max_elements: int = 3000,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_check_joins"
        try:
            args = _selection(ids, tag, categories)
            args["allow_free_ids"] = _int_list(allow_free_ids)
            args["max_elements"] = int(max_elements)
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        parsed, elapsed, early = _execute(tool, "check_joins.ipy", args, tool_executor)
        if early is not None or parsed is None:
            return early or {}
        return _finish(
            tool,
            parsed,
            elapsed,
            page,
            workspace,
            row_types={"wall_id": "int", "end": "int", "joined_to": "intlist", "x_m": "float", "y_m": "float"},
            sort_key=lambda r: (r.get("status") != "unjoined", r.get("wall_id") or 0, r.get("end") or 0),
        )

    def check_intersections(
        self,
        set_a: Optional[Dict[str, Any]] = None,
        set_b: Optional[Dict[str, Any]] = None,
        tolerance_m: float = 0.0,
        min_volume_m3: float = 0.0005,
        mode: str = "solid",
        max_pairs: int = 20000,
        time_budget_s: float = 20.0,
        skip_hosted: bool = True,
        max_elements: int = 3000,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_check_intersections"
        if mode not in ("solid", "bbox"):
            return _bad_input(tool, ValueError("mode must be 'solid' or 'bbox'"))
        try:
            a = set_a or {}
            args: Dict[str, Any] = {
                "set_a": _selection(a.get("ids"), a.get("tag"), a.get("categories")),
                "set_b": None,
                "tolerance_m": float(tolerance_m),
                "min_volume_m3": float(min_volume_m3),
                "mode": mode,
                "max_pairs": max(1, int(max_pairs)),
                "time_budget_s": max(1.0, min(float(time_budget_s), 25.0)),
                "skip_hosted": bool(skip_hosted),
                "max_elements": int(max_elements),
            }
            if set_b:
                args["set_b"] = _selection(set_b.get("ids"), set_b.get("tag"), set_b.get("categories"))
        except (TypeError, ValueError, AttributeError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        parsed, elapsed, early = _execute(tool, "check_intersections.ipy", args, tool_executor)
        if early is not None or parsed is None:
            return early or {}
        return _finish(
            tool,
            parsed,
            elapsed,
            page,
            workspace,
            row_types={"a_id": "int", "b_id": "int", "volume_m3": "float", "x_m": "float", "y_m": "float", "z_m": "float"},
            sort_key=lambda r: (-(r.get("volume_m3") or 0.0), r.get("a_id") or 0, r.get("b_id") or 0),
        )

    def check_orientation(
        self,
        ids: Optional[List[int]] = None,
        tag: str = "",
        categories: Optional[List[str]] = None,
        scope: str = "exterior",
        distance_m: float = 0.6,
        height_m: float = 1.0,
        max_elements: int = 3000,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_check_orientation"
        if scope not in ("exterior", "all"):
            return _bad_input(tool, ValueError("scope must be 'exterior' or 'all'"))
        try:
            args = _selection(ids, tag, categories)
            args.update(
                scope=scope,
                distance_m=max(0.05, float(distance_m)),
                height_m=max(0.1, float(height_m)),
                max_elements=int(max_elements),
            )
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        parsed, elapsed, early = _execute(tool, "check_orientation.ipy", args, tool_executor)
        if early is not None or parsed is None:
            return early or {}
        return _finish(
            tool,
            parsed,
            elapsed,
            page,
            workspace,
            row_types={"wall_id": "int", "exterior_room_id": "int", "interior_room_id": "int", "x_m": "float", "y_m": "float"},
            sort_key=lambda r: (r.get("status") != "exterior_in_room", r.get("wall_id") or 0),
        )

    # -- generic runner for the newer tools ---------------------------------- #
    def _run(
        self,
        tool: str,
        script: str,
        args: Dict[str, Any],
        page: PageSpec,
        workspace: Any,
        tool_executor: Optional[ToolExecutor],
        row_types: Dict[str, str],
        sort_key: Any,
    ) -> Dict[str, Any]:
        if tool != "revit_check_levels_grids" and not any(args.get(k) for k in ("ids", "tag", "categories", "name", "system")):
            return _bad_input(tool, ValueError("give ids, a tag, categories, or a family/system name"))
        parsed, elapsed, early = _execute(tool, script, args, tool_executor)
        if early is not None or parsed is None:
            return early or {}
        if parsed.meta.get("partial") == "1" or any(i.startswith(("UNVERIFIED", "NO_CONNECTORS:")) for i in parsed.infos):
            parsed.meta["verified"] = "0"
        return _finish(tool, parsed, elapsed, page, workspace, row_types=row_types, sort_key=sort_key)

    def audit_openings(
        self,
        ids: Optional[List[int]] = None,
        tag: str = "",
        categories: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        pos_tol_m: float = 0.08,
        ray_test: bool = True,
        swing: bool = True,
        max_elements: int = 3000,
        time_budget_s: float = 15.0,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_audit_openings"
        try:
            args = _selection(ids, tag, categories)
            args.update(
                data=_clean_data(data) if data else None,
                pos_tol_m=max(0.001, float(pos_tol_m)),
                ray_test=bool(ray_test),
                swing=bool(swing),
                max_elements=int(max_elements),
                time_budget_s=_budget(time_budget_s, 15.0),
            )
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        return self._run(
            tool,
            "audit_openings.ipy",
            args,
            page,
            workspace,
            tool_executor,
            {"id": "int", "host_id": "int", "along_m": "float", "wall_len_m": "float", "width_m": "float", "height_m": "float", "sill_m": "float", "head_m": "float"},
            lambda r: (r.get("status") == "ok", r.get("id") or 0),
        )

    def audit_roofs(
        self,
        ids: Optional[List[int]] = None,
        tag: str = "",
        categories: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        cover_ids: Optional[List[int]] = None,
        cover_tag: str = "",
        top_on_level: bool = False,
        top_tol_m: float = 0.05,
        parapet_min_height_m: float = 0.6,
        parapet_dist_m: float = 0.35,
        max_slope_deg: float = 60.0,
        check_stairs: bool = True,
        max_elements: int = 3000,
        time_budget_s: float = 15.0,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_audit_roofs"
        try:
            args = _selection(ids, tag, categories)
            args.update(
                data=_clean_data(data) if data else None,
                cover_ids=_int_list(cover_ids),
                cover_tag=_tag(cover_tag),
                top_on_level=bool(top_on_level),
                top_tol_m=max(0.001, float(top_tol_m)),
                parapet_min_height_m=max(0.05, float(parapet_min_height_m)),
                parapet_dist_m=max(0.05, float(parapet_dist_m)),
                max_slope_deg=max(1.0, float(max_slope_deg)),
                check_stairs=bool(check_stairs),
                max_elements=int(max_elements),
                time_budget_s=_budget(time_budget_s, 15.0),
            )
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        return self._run(
            tool,
            "audit_roofs.ipy",
            args,
            page,
            workspace,
            tool_executor,
            {"id": "int", "level_z_m": "float", "top_m": "float", "bottom_m": "float", "max_slope_deg": "float", "min_slope_deg": "float", "plan_area_m2": "float", "flat": "bool"},
            lambda r: (r.get("status") == "ok", r.get("id") or 0),
        )

    def probe_family(
        self,
        name: str = "",
        ids: Optional[List[int]] = None,
        deep: bool = True,
        allow_nested: bool = False,
        expect_connectors: bool = False,
        max_families: int = 3,
        max_symbols: int = 12,
        time_budget_s: float = 18.0,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_probe_family"
        try:
            fam_name = _tag(name)
            id_list = _int_list(ids)
            if not fam_name and not id_list:
                raise ValueError("give name (family or type name) or ids (family, type or instance ids)")
            args = {
                "name": fam_name,
                "ids": id_list,
                "deep": bool(deep),
                "allow_nested": bool(allow_nested),
                "expect_connectors": bool(expect_connectors),
                "max_families": max(1, min(int(max_families), 10)),
                "max_symbols": max(1, min(int(max_symbols), 50)),
                "time_budget_s": _budget(time_budget_s, 18.0),
            }
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        order = {"family": 0, "nested": 1, "nested_family": 2, "connector": 3, "extent": 4, "type": 5, "param": 6}
        return self._run(
            tool,
            "probe_family.ipy",
            args,
            page,
            workspace,
            tool_executor,
            {"id": "int", "types": "int", "instances": "int", "solids": "int"},
            lambda r: (order.get(str(r.get("kind")), 9), str(r.get("family") or "")),
        )

    def system_report(
        self,
        system: str = "",
        ids: Optional[List[int]] = None,
        tag: str = "",
        categories: Optional[List[str]] = None,
        allow_open_ids: Optional[List[int]] = None,
        max_elements: int = 5000,
        time_budget_s: float = 18.0,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_system_report"
        try:
            args = _selection(ids, tag, categories)
            args.update(
                system=_tag(system),
                allow_open_ids=_int_list(allow_open_ids),
                max_elements=int(max_elements),
                time_budget_s=_budget(time_budget_s, 18.0),
            )
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        return self._run(
            tool,
            "system_report.ipy",
            args,
            page,
            workspace,
            tool_executor,
            {"element_id": "int", "members": "int", "curves": "int", "fittings": "int", "equipment": "int", "open_ends": "int",
             "disconnected_fittings": "int", "unconnected_ports": "int", "flow_mismatch": "int", "size_mismatch": "int",
             "islands": "int", "x_m": "float", "y_m": "float", "z_m": "float"},
            lambda r: (r.get("kind") != "system", str(r.get("system") or ""), r.get("element_id") or 0),
        )

    def check_naming_and_params(
        self,
        ids: Optional[List[int]] = None,
        tag: str = "",
        categories: Optional[List[str]] = None,
        required: Optional[List[str]] = None,
        unique: Optional[List[str]] = None,
        name_pattern: str = "",
        name_target: str = "type",
        max_elements: int = 3000,
        time_budget_s: float = 15.0,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_check_naming_and_params"
        if name_target not in ("type", "element"):
            return _bad_input(tool, ValueError("name_target must be 'type' or 'element'"))
        try:
            args = _selection(ids, tag, categories)
            args.update(
                required=_names(required, "required"),
                unique=_names(unique if unique is not None else ["Mark"], "unique"),
                name_pattern=_tag(name_pattern),
                name_target=name_target,
                max_elements=int(max_elements),
                time_budget_s=_budget(time_budget_s, 15.0),
            )
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        return self._run(
            tool,
            "check_naming_and_params.ipy",
            args,
            page,
            workspace,
            tool_executor,
            {"id": "int"},
            lambda r: (str(r.get("category") or ""), str(r.get("problem") or ""), r.get("id") or 0),
        )

    def check_levels_grids(
        self,
        tolerance_mm: float = 5.0,
        require_ceiling_plan: bool = False,
        max_elements: int = 3000,
        time_budget_s: float = 15.0,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_check_levels_grids"
        try:
            args = {
                "tolerance_mm": max(0.0, float(tolerance_mm)),
                "require_ceiling_plan": bool(require_ceiling_plan),
                "max_elements": int(max_elements),
                "time_budget_s": _budget(time_budget_s, 15.0),
            }
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        return self._run(
            tool,
            "check_levels_grids.ipy",
            args,
            page,
            workspace,
            tool_executor,
            {"id": "int", "elevation_m": "float", "plan_views": "int", "ceiling_plans": "int", "x0_m": "float", "y0_m": "float", "x1_m": "float", "y1_m": "float"},
            lambda r: (r.get("kind") != "level", r.get("elevation_m") or 0.0, r.get("id") or 0),
        )

    def review(
        self,
        tag: str = "",
        ids: Optional[List[int]] = None,
        baseline_id: str = "",
        checks: Optional[List[str]] = None,
        cover_tag: str = "",
        system: str = "",
        required: Optional[List[str]] = None,
        unique: Optional[List[str]] = None,
        openings_data: Optional[Dict[str, Any]] = None,
        roofs_data: Optional[Dict[str, Any]] = None,
        allow_free_ids: Optional[List[int]] = None,
        time_budget_s: float = 90.0,
        max_fails_per_check: int = 10,
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_review"
        wanted = list(checks) if checks else list(REVIEW_CHECKS)
        unknown = [c for c in wanted if c not in REVIEW_CHECKS]
        if unknown:
            return _bad_input(tool, ValueError(f"unknown check(s) {unknown}; choose from {list(REVIEW_CHECKS)}"))
        try:
            scope_tag = _tag(tag)
            scope_ids = _int_list(ids)
            base = (baseline_id or "").strip()
            if base and not is_safe_name(base):
                raise ValueError("baseline_id must be the id returned by revit_warnings_delta (letters, digits, - and _)")
            cap = max(1, min(int(max_fails_per_check), 100))
            budget = max(5.0, min(float(time_budget_s), 600.0))
            common = {"workspace": workspace, "tool_executor": tool_executor, "limit": 500}
            sel = {"ids": scope_ids, "tag": scope_tag}
            openings_args = dict(sel, data=openings_data)
            roofs_args = dict(sel, data=roofs_data, cover_tag=_tag(cover_tag))
            if openings_data:
                _clean_data(openings_data)
            if roofs_data:
                _clean_data(roofs_data)
            naming_args = dict(sel, required=_names(required, "required"), unique=unique)
            if not scope_ids:
                naming_args["categories"] = ["Doors", "Windows", "Rooms"]
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        if _server_in_mock_mode():
            return mock_result(tool)

        needs_scope = {"joins", "orientation", "intersections", "openings", "roofs", "naming_params", "systems"}
        started = time.perf_counter()
        table: List[Dict[str, Any]] = []
        all_fails: List[str] = []
        shown_fails: List[str] = []
        not_verified: List[str] = []
        skipped: List[str] = []
        doc_info: Dict[str, Any] = {}
        revit_version: Optional[str] = None
        more_than_cap = False
        stop_reason = ""

        def run_one(name: str) -> Optional[Dict[str, Any]]:
            if name == "joins":
                return self.check_joins(ids=scope_ids, tag=scope_tag, allow_free_ids=allow_free_ids, **common)
            if name == "orientation":
                return self.check_orientation(ids=scope_ids, tag=scope_tag, **common)
            if name == "intersections":
                remaining = budget - (time.perf_counter() - started)
                return self.check_intersections(
                    set_a={"ids": scope_ids, "tag": scope_tag}, time_budget_s=max(1.0, min(10.0, remaining)), **common
                )
            if name == "openings":
                return self.audit_openings(**openings_args, **common)
            if name == "roofs":
                return self.audit_roofs(**roofs_args, **common)
            if name == "levels_grids":
                return self.check_levels_grids(**common)
            if name == "naming_params":
                return self.check_naming_and_params(**naming_args, **common)
            if name == "systems":
                return self.system_report(ids=scope_ids, tag=scope_tag, system=system, **common)
            if name == "warnings":
                return self.warnings_delta(baseline_id=base, tag_prefix=scope_tag, **common)
            return None

        for name in wanted:
            entry: Dict[str, Any] = {"check": name, "status": "", "fails": 0, "summary": "", "elapsed_ms": 0}
            table.append(entry)
            if stop_reason:
                entry.update(status="not_verified", summary=stop_reason)
                not_verified.append(f"{name}: not run ({stop_reason})")
                continue
            if name in needs_scope and not (scope_tag or scope_ids):
                entry.update(status="not_verified", summary="needs tag or ids")
                not_verified.append(f"{name}: not run (give tag or ids)")
                continue
            if name == "warnings" and not base:
                entry.update(status="not_verified", summary="no baseline_id")
                not_verified.append("warnings: new warnings were not compared (no baseline_id; call revit_warnings_delta before the phase and pass its baseline_id)")
                continue
            if time.perf_counter() - started > budget:
                entry.update(status="not_verified", summary="time budget used up")
                not_verified.append(f"{name}: not run (time_budget_s={budget:g} used up)")
                continue
            t0 = time.perf_counter()
            r = run_one(name) or {}
            entry["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
            if r.get("mock"):
                return mock_result(tool)
            if not r.get("ok"):
                kind = str(r.get("kind") or "error")
                message = str(r.get("message") or "")
                entry["summary"] = f"{kind}: {message}"[:160]
                if kind == "empty_selection":
                    entry["status"] = "skipped"
                    skipped.append(f"{name}: nothing to check ({message[:120]})")
                    not_verified.append(f"{name}: no elements were checked ({message[:120]})")
                else:
                    entry["status"] = "not_verified"
                    not_verified.append(f"{name}: {kind}: {message[:160]}")
                    if kind in ("no_bridge", "bridge_error", "approval_required", "timeout_running"):
                        stop_reason = f"stopped after {kind} in {name}"
                continue
            if not doc_info.get("title") and (r.get("document") or {}).get("title"):
                doc_info = dict(r["document"])
            revit_version = revit_version or r.get("revit_version")
            n_fail = int((r.get("counts") or {}).get("fails", len(r.get("fails", []))))
            entry.update(fails=n_fail, summary=str(r.get("summary") or ""), verified=r.get("verified", True), partial=bool((r.get("limits") or {}).get("partial")))
            lines = [f"{name}: {line}" for line in r.get("fails", [])]
            all_fails.extend(lines)
            shown_fails.extend(lines[:cap])
            if n_fail > cap:
                more_than_cap = True
            for line in r.get("info", []):
                if str(line).startswith("UNVERIFIED"):
                    not_verified.append(f"{name}: {line}")
            if r.get("verified") is False:
                not_verified.append(f"{name}: {r.get('summary')}")
            if entry["partial"]:
                not_verified.append(f"{name}: partial result, stopped at its time or pair budget")
            if r.get("detail_file"):
                entry["detail_file"] = r["detail_file"]
            entry["status"] = "fail" if n_fail else ("not_verified" if not entry["verified"] or entry["partial"] else "pass")

        total_fails = sum(int(e.get("fails", 0)) for e in table)
        verdict = "FAIL" if total_fails else ("INCOMPLETE" if not_verified else "PASS")
        failing = [f"{e['check']} {e['fails']}" for e in table if e.get("fails")]
        n_pass = sum(1 for e in table if e["status"] == "pass")
        text = f"{verdict}: {total_fails} FAIL"
        if failing:
            text += " (" + ", ".join(failing) + ")"
        text += f"; {n_pass} checks clean, {len(not_verified)} things could not be verified"
        if skipped:
            text += f", {len(skipped)} skipped (nothing to check)"
        rows = [dict((k, str(v)) for k, v in e.items()) for e in table]
        synthetic = ScriptOutput(
            summary=text,
            fails=shown_fails,
            infos=[],
            rows=rows,
            meta={"doc_title": doc_info.get("title") or "", "doc_guid": doc_info.get("guid") or "", "revit_version": revit_version or "", "verified": "0" if not_verified else "1"},
            counts={"fail": len(shown_fails), "info": 0, "row": len(rows)},
        )
        page = PageSpec.from_args(limit, offset, count_only, fields)
        elapsed = int((time.perf_counter() - started) * 1000)
        result = assemble_result(
            tool,
            synthetic,
            page,
            elapsed_ms=elapsed,
            workspace=workspace,
            summary=text,
            extra={
                "verdict": verdict,
                "checks": table,
                "not_verified": not_verified,
                "skipped": skipped,
                "not_included": ["renders: framed images are not part of this review yet (upgrade plan item 1.10); look at the model yourself or use revit_export_image"],
                "fails_total": total_fails,
            },
            row_types={"fails": "int", "elapsed_ms": "int", "verified": "bool", "partial": "bool"},
        )
        if more_than_cap or len(all_fails) > len(shown_fails):
            header = [f"tool: {tool}", f"document: {doc_info.get('title') or ''} {doc_info.get('guid') or ''}".rstrip(), f"summary: {text}"]
            path, why = write_detail_file(workspace, tool, header, all_fails, not_verified, rows)
            result["detail_file"] = path
            result["limits"]["truncated"] = True
            result["limits"]["fails_shown_per_check"] = cap
            if why:
                result["limits"]["detail_file_error"] = why
        return result

    def warnings_delta(
        self,
        baseline_id: str = "",
        tag_prefix: str = "",
        limit: int = 50,
        offset: int = 0,
        count_only: bool = False,
        fields: Optional[List[str]] = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_warnings_delta"
        baseline_id = (baseline_id or "").strip()
        if baseline_id and not is_safe_name(baseline_id):
            return _bad_input(tool, ValueError("baseline_id must be the id returned by an earlier snapshot (letters, digits, - and _)"))
        try:
            prefix = _tag(tag_prefix)
        except ValueError as exc:
            return _bad_input(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)

        baseline: Optional[Dict[str, Any]] = None
        if baseline_id:
            baseline, why = load_json(workspace, f"warnings_baseline_{baseline_id}")
            if baseline is None or not isinstance(baseline.get("warnings"), list):
                return error_result(
                    tool,
                    "baseline_not_found",
                    f"Baseline '{baseline_id}' could not be read ({why or 'invalid content'}).",
                    hint="Call revit_warnings_delta without baseline_id to take a new baseline (the id is returned), then pass it later.",
                )

        parsed, elapsed, early = _execute(tool, "warnings_dump.ipy", {"want_tags": bool(baseline_id)}, tool_executor)
        if early is not None or parsed is None:
            return early or {}
        current = [_warning_from_row(r) for r in parsed.rows]
        doc = {"title": parsed.meta.get("doc_title"), "guid": parsed.meta.get("doc_guid")}

        if baseline is None:
            return self._take_baseline(tool, parsed, current, doc, elapsed, page, workspace)
        return self._diff_baseline(tool, baseline_id, baseline, parsed, current, doc, elapsed, page, workspace, prefix)

    # -- warnings helpers --------------------------------------------------- #
    def _take_baseline(
        self,
        tool: str,
        parsed: ScriptOutput,
        current: List[Dict[str, Any]],
        doc: Dict[str, Any],
        elapsed: int,
        page: PageSpec,
        workspace: Any,
    ) -> Dict[str, Any]:
        new_id = new_baseline_id()
        payload = {
            "baseline_id": new_id,
            "document": doc,
            "warnings": [{"severity": w["severity"], "description": w["description"], "ids": w["ids"]} for w in current],
        }
        path, why = save_json(workspace, f"warnings_baseline_{new_id}", payload)
        if path is None:
            return error_result(
                tool,
                "baseline_not_saved",
                why or "the baseline could not be saved",
                hint="The baseline is stored in the workspace folder; check that the workspace exists and is writable.",
            )
        groups = Counter(w["description"] for w in current)
        infos = [f"{n} x {desc}" for desc, n in groups.most_common(5)]
        by_sev = Counter(w["severity"] for w in current)
        sev_text = ", ".join(f"{n} {s}" for s, n in sorted(by_sev.items())) or "none"
        summary = f"Baseline {new_id} saved: {len(current)} warnings ({sev_text}) in {len(groups)} groups"
        synthetic = ScriptOutput(summary=summary, infos=infos, meta=dict(parsed.meta), counts={"fail": 0, "info": len(infos), "row": 0})
        return assemble_result(
            tool,
            synthetic,
            page,
            elapsed_ms=elapsed,
            workspace=workspace,
            summary=summary,
            extra={
                "baseline_id": new_id,
                "baseline_file": path,
                "warnings_total": len(current),
                "next": f"After the phase, call revit_warnings_delta with baseline_id='{new_id}'.",
            },
        )

    def _diff_baseline(
        self,
        tool: str,
        baseline_id: str,
        baseline: Dict[str, Any],
        parsed: ScriptOutput,
        current: List[Dict[str, Any]],
        doc: Dict[str, Any],
        elapsed: int,
        page: PageSpec,
        workspace: Any,
        prefix: str,
    ) -> Dict[str, Any]:
        b_doc = baseline.get("document") or {}
        same_doc = (
            b_doc.get("guid") == doc.get("guid")
            if (b_doc.get("guid") and doc.get("guid"))
            else (b_doc.get("title") or "") == (doc.get("title") or "")
        )
        if not same_doc:
            return error_result(
                tool,
                "document_mismatch",
                f"Baseline {baseline_id} was taken in '{b_doc.get('title')}', the open document is '{doc.get('title')}'.",
                hint="Warnings of different documents cannot be compared. Open the right document or take a new baseline.",
            )
        before = [
            {"severity": str(w.get("severity", "")), "description": str(w.get("description", "")), "ids": [int(i) for i in w.get("ids", [])]}
            for w in baseline["warnings"]
        ]
        c_now = Counter(_warning_key(w) for w in current)
        c_then = Counter(_warning_key(w) for w in before)
        new_keys, closed_keys = c_now - c_then, c_then - c_now

        def expand(items: List[Dict[str, Any]], budget: "Counter[str]") -> List[Dict[str, Any]]:
            out, left = [], Counter(budget)
            for w in items:
                key = _warning_key(w)
                if left[key] > 0:
                    left[key] -= 1
                    out.append(w)
            return out

        new_w, closed_w = expand(current, new_keys), expand(before, closed_keys)

        fails: List[str] = []
        infos: List[str] = []
        owned = 0
        for w in new_w:
            line = f"NEW_WARNING: {w['description']} [{w['severity']}] ids={','.join(str(i) for i in w['ids'][:12])}"
            is_owned = (not prefix) or any(t.startswith(prefix) for t in w["tags"])
            if is_owned:
                owned += 1
                fails.append(line)
            else:
                infos.append(line)
        rows: List[Dict[str, str]] = [
            {"change": "new", "severity": w["severity"], "description": w["description"], "ids": ",".join(map(str, w["ids"])), "tags": "|".join(w["tags"])}
            for w in new_w
        ] + [
            {"change": "closed", "severity": w["severity"], "description": w["description"], "ids": ",".join(map(str, w["ids"])), "tags": ""}
            for w in closed_w
        ]
        summary = f"{len(new_w)} new, {len(closed_w)} closed warnings since {baseline_id} (was {len(before)}, now {len(current)})"
        if prefix:
            summary += f"; {owned} new on elements tagged '{prefix}'"
        synthetic = ScriptOutput(
            summary=summary,
            fails=fails,
            infos=infos,
            rows=rows,
            meta=dict(parsed.meta),
            counts={"fail": len(fails), "info": len(infos), "row": len(rows)},
        )
        return assemble_result(
            tool,
            synthetic,
            page,
            row_types={"ids": "intlist"},
            elapsed_ms=elapsed,
            workspace=workspace,
            summary=summary,
            extra={
                "baseline_id": baseline_id,
                "warnings_delta": {"new": len(new_w), "closed": len(closed_w)},
                "warnings_now": len(current),
                "warnings_baseline": len(before),
            },
        )


def _warning_from_row(row: Dict[str, str]) -> Dict[str, Any]:
    ids: List[int] = []
    for part in (row.get("ids") or "").split(","):
        if part.strip().lstrip("-").isdigit():
            ids.append(int(part))
    tags = [t for t in (row.get("tags") or "").split("|") if t]
    return {
        "severity": row.get("severity", ""),
        "description": row.get("description", ""),
        "ids": sorted(set(ids)),
        "tags": tags,
    }


def _warning_key(w: Dict[str, Any]) -> str:
    return f"{w['description']}|{','.join(str(i) for i in sorted(w['ids']))}"
