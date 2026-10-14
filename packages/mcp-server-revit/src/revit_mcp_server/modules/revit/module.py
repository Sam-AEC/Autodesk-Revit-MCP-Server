"""
revit module - read-only "eyes" for an AI working in a live Revit session (Phase 1 of
docs/upgrade-plan-hands-and-eyes.md).

Commands (tool names are ``revit_<command>``):
  check_joins         1.2  per wall end: joined or not, to which walls, join type
  check_intersections 1.3  solid/solid overlap volumes (BooleanOperationsUtils); mode=bbox kept
  warnings_delta      1.8  snapshot a warnings baseline, later list new / closed warnings
  check_orientation   1.9  probe 0.6 m along each exterior wall's Orientation, flag walls facing into a room

How it works: each command is thin. It builds an IronPython 2.7 script from ``scripts/_prelude.ipy`` plus one
tool script, injects the arguments as an ``ARGS`` literal, runs it inside Revit and turns the printed line
protocol into the contract of plan section 6 (``revit_mcp_server.check_contract``): summary, FAIL lines, INFO
lines, pageable rows, and a detail file in the workspace when lists are long. The scripts never open a
transaction. Output is capped (default 50 rows; limit / offset / count_only / fields).

The seam: ``run_readonly_script`` is the ONLY place that sends the script to Revit. It uses the existing
``revit_execute_python`` tool. That tool is still declared mutating and gated in this build, so with approval
mode "required" these tools answer ``kind: approval_required`` until the read-mode work (plan item 0.6) makes
``revit_execute_python`` accept ``mode: "read"`` without a plan. Only that one function needs to change then.

Everything that needs a running Revit with the add-in is UNVERIFIED here: the scripts are syntax-checked and
exercised against a stub of the Revit API in the tests, not against Revit.
"""
from __future__ import annotations

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
)

SCRIPT_DIR = Path(__file__).resolve().parent / "scripts"
PRELUDE = "_prelude.ipy"
EXECUTE_TOOL = "revit_execute_python"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

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
    body = (SCRIPT_DIR / script_name).read_text(encoding="utf-8")
    return f"{prelude}\n\nARGS = {ascii(args)}\n\n{body}\n"


def run_readonly_script(script: str, tool_executor: ToolExecutor) -> Any:
    """Send a read-only IronPython script to Revit and return the bridge's raw answer.

    THE SEAM. Today this calls ``revit_execute_python``, which the server gates as mutating. When the
    ``mode: "read"`` work lands, the ``mode`` key below is what makes that call ungated; nothing else in
    this module should need to change. (The key is ignored by builds that do not know it.)
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
