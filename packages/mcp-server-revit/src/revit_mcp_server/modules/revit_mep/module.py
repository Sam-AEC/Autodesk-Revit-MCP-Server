"""
revit_mep module - data-driven MEP routing, connecting and electrical circuits for a live Revit session.

It turns the hand-written recipes of docs/recipes/villa2 (m3_route.py, m4_heating.py, m7_electrical.py) into tools that
take plain data: a list of routes, connections or circuits. The families come from the project (see
docs/recipes/villa2/m1_specs.json for the AMB2_* families and their ports); no category is preferred.

Commands (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  check_elements   read-only  dry run of the category guard: would these elements be accepted for this system?
  route            WRITE      pipe or duct between two connectors or points, with elbows, unions, transitions, takeoffs, tees
  connect          WRITE      join two touching connectors (direct, union, transition or elbow); reports open ends
  circuit          WRITE      native electrical circuits (ElectricalSystem.Create) from elements and a panel

The category guard (every tool, before anything is changed): an element may take part in a pipe, duct or electrical
system only when its CATEGORY is an MEP category of that domain and it really has a connector of the requested system.
A family that fails is refused with a clear code (category_mismatch, no_connectors, domain_mismatch, system_mismatch,
no_free_connector) and the whole call stops before the first change. It is never placed "anyway". A system name that
belongs to another domain than the tool's kind (for example a heating system on a duct route) is refused here, before
any script is sent.

How it works: the same seam as ``revit_docs`` (read its module.py header). Each command builds an IronPython 2.7 script
from the revit module's ``_prelude.ipy``, the revit_docs ``_tags_read.ipy`` and ``_write_prelude.ipy`` (Runner, Collector,
ownership tags: reused, not copied) and this module's ``_mep_guard.ipy``, ``_mep_write.ipy`` and the command script,
injects the arguments as an ``ARGS`` literal, runs it in Revit, and turns the printed line protocol into the plan section 6
contract (``revit_mcp_server.check_contract``).

Safety of the write commands (same rules as revit_docs):
  * ``is_mutating`` in module.json: the approval gate demands an approved plan_id first; that one approval covers the
    vetted scripts and the read-only revit_system_report run that follows (ModuleProvider hands the command
    ``approved_executor``, which can call revit_execute_python only);
  * one TransactionGroup per call, one Transaction per route / connection / circuit; on_error 'abort' (default) rolls the
    whole group back on the first failure and returns ok:false with the failing element ids and Revit's message;
    'skip' keeps what worked and lists the rest; Revit warnings are dismissed and listed in ``info``;
  * a call replaces only elements that carry its own Extensible Storage tag (tag + key) and never deletes anything else;
    a replacement that would delete foreign dependents is refused;
  * results carry ``changed_ids``, ``post_check`` and ``verified``, and are never ``ok: true`` when a post-check fails.

Post-check: the script verifies its own work inside the group (pieces exist and carry the tag, requested connectors are
connected, no unplanned open end, sizes and system class as asked, circuit membership/panel/name). After the group is
committed this module runs the existing read-only ``revit_system_report`` (modules/revit, not rewritten) on the created
pipes, ducts and fittings and adds its verdict as one more post-check; revit_mep_connect lists the open ends it finds.

UNVERIFIED: nothing here has run against a live Revit. The scripts are syntax-checked and exercised against a stub of
the Revit API (tests/revit_mep_stub.py, tests/test_revit_mep*.py), which proves the control flow, the guard, the
rollback behaviour and the line protocol, not that Revit accepts the calls. Specifically unproven in a live model:
Pipe.Create / Duct.Create overloads with connectors, NewElbowFitting / NewUnionFitting / NewTransitionFitting on the
generated pieces, NewTakeoffFitting, PlumbingUtils / MechanicalUtils.BreakCurve + NewTeeFitting, setting size by
built-in parameter after creation, system-type lookup by SystemClassification, ElectricalSystem.Create + SelectPanel +
Load Name, and reading BaseEquipment / Elements.Size back. Treat the first real run as a trial on a scratch model.
"""
from __future__ import annotations

import importlib.util
import math
import re
import sys
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

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
REVIT_MODULE_DIR = MODULE_DIR.parent / "revit"
DOCS_SCRIPT_DIR = MODULE_DIR.parent / "revit_docs" / "scripts"
REVIT_PRELUDE = REVIT_MODULE_DIR / "scripts" / "_prelude.ipy"
TAGS_READ = DOCS_SCRIPT_DIR / "_tags_read.ipy"
WRITE_PRELUDE = DOCS_SCRIPT_DIR / "_write_prelude.ipy"
GUARD = "_mep_guard.ipy"
WRITE_HELPERS = "_mep_write.ipy"
EXECUTE_TOOL = "revit_execute_python"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

# script name -> (write script?, needs _mep_write.ipy?)
SCRIPTS: Dict[str, Tuple[bool, bool]] = {
    "route.ipy": (True, True),
    "connect.ipy": (True, True),
    "circuit.ipy": (True, False),
    "check_elements.ipy": (False, False),
}

_TAG = re.compile(r"^[ -~]{1,80}$")  # printable ASCII only
_IDENT = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
_BAD_NAME_CHARS = set("\\:{}[]|;<>?`~")

# --------------------------------------------------------------------------- #
# Systems: short keys (as in docs/recipes/villa2/m1_specs.json) and the Revit names behind them
# --------------------------------------------------------------------------- #
REVIT_SYSTEMS: Dict[str, Tuple[str, ...]] = {
    "pipe": ("DomesticColdWater", "DomesticHotWater", "Sanitary", "Vent", "SupplyHydronic", "ReturnHydronic",
             "FireProtectWet", "FireProtectDry", "FireProtectPreaction", "FireProtectOther", "OtherPipe"),
    "duct": ("SupplyAir", "ReturnAir", "ExhaustAir", "OtherAir"),
    "elec": ("PowerCircuit", "Data", "Telephone", "Security", "FireAlarm", "NurseCall", "Controls", "Communication",
             "PowerBalanced", "PowerUnBalanced"),
}
SYSTEM_KEYS: Dict[str, Tuple[str, str]] = {
    "cold": ("pipe", "DomesticColdWater"), "hot": ("pipe", "DomesticHotWater"), "san": ("pipe", "Sanitary"),
    "vent": ("pipe", "Vent"), "hsup": ("pipe", "SupplyHydronic"), "hret": ("pipe", "ReturnHydronic"),
    "supply": ("duct", "SupplyAir"), "return": ("duct", "ReturnAir"), "exhaust": ("duct", "ExhaustAir"),
    "outdoor": ("duct", "OtherAir"), "power": ("elec", "PowerCircuit"), "data": ("elec", "Data"),
}
KIND_LABEL = {"pipe": "piping", "duct": "duct", "elec": "electrical"}
GUARD_CODES = ("category_mismatch", "no_connectors", "domain_mismatch", "system_mismatch", "no_free_connector")

_GUARD_HINT = (
    "The family is not usable for this system. Run revit_mep_check_elements to see its category and connectors, "
    "place the right family (see revit_probe_family for an unplaced one), or fix its category / connectors. Nothing was changed."
)
_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "domain_mismatch": "The system and the tool do not belong together (or the family has connectors of another domain only). Pick a system of the tool's kind: pipe systems for pipes, air systems for ducts. Nothing was changed.",
    "category_mismatch": _GUARD_HINT,
    "no_connectors": _GUARD_HINT,
    "system_mismatch": _GUARD_HINT,
    "no_free_connector": "Every matching connector is already connected. Free one, choose another system, or replace the route that uses it (same tag and id). Nothing was changed.",
    "element_not_found": "Check the element ids or Marks (a Mark must belong to exactly one element). Nothing was changed.",
    "connector_not_found": "No connector matches the filters. Loosen diameter_mm, sort, index or near_m. Nothing was changed.",
    "connector_in_use": "That connector is connected to something else. Choose another with near_m, sort or index. Nothing was changed.",
    "level_not_found": "List the levels with revit_list_levels and use the exact name. Nothing was changed.",
    "type_not_found": "Use one of the pipe or duct type names listed in the message. Nothing was changed.",
    "system_type_not_found": "Start the route at a connector, or create the system type in Revit first. Nothing was changed.",
    "trunk_not_found": "Build the trunk route first (earlier in the same call, or an earlier call with the same tag), or list real pipe or duct ids. Nothing was changed.",
    "tee_needs_owned_trunk": "Use branch_to.route for a tee, or fitting 'takeoff' for a trunk given by ids. Nothing was changed.",
    "duplicate_route_id": "Give every route in the call its own id. Nothing was changed.",
    "duplicate_connection_id": "Give every connection in the call its own id. Nothing was changed.",
    "duplicate_circuit_id": "Give every circuit in the call its own id. Nothing was changed.",
    "not_coincident": "This tool does not move or route anything. Use revit_mep_route to run a pipe or duct between the two connectors. Nothing was changed.",
    "flow_mismatch": "Both connectors have the same flow direction (both In or both Out). Pick the other connector. Nothing was changed.",
    "facing_same_way": "The two connectors point the same way. Check the pieces; nothing was changed.",
    "joint_needs_curves": "Use joint 'direct' (or 'auto') to join equipment. Nothing was changed.",
    "same_element": "a and b must be different elements. Nothing was changed.",
    "already_on_circuit": "The element is on a circuit this tool did not make. Remove it from that circuit in Revit first; this tool never moves elements between circuits. Nothing was changed.",
    "panel_category": "The panel must be an Electrical Equipment family. Nothing was changed.",
    "panel_in_circuit": "Remove the panel from the element list. Nothing was changed.",
    "element_in_two_circuits": "An element can be on one circuit of a system. Nothing was changed.",
    "empty_circuit": "List at least one element. Nothing was changed.",
    "rolled_back": "Nothing was changed: the whole call was rolled back. Fix the cause named in fails and call again, or pass on_error='skip' to keep what worked.",
    "partial_failure": "The steps that worked were kept (see changed_ids); the failed ones are in fails with element ids. Run the same call again to replace what this tool made, or fix the cause first.",
    "post_check_failed": "The model changed but a check afterwards failed (see post_check). Inspect the listed ids with revit_system_report, or run the call again to replace what this tool made.",
    "script_exception": "The embedded script failed inside Revit; any open transaction group was rolled back, so the model should be unchanged (verify with revit_warnings_delta).",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id, and do not repeat a write until it has finished.",
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
    """Prelude(s) + ``ARGS`` literal + the command script. Read scripts get no write prelude."""
    write, needs_helpers = SCRIPTS[script_name]
    parts = [REVIT_PRELUDE.read_text(encoding="utf-8")]
    if write:
        parts.append(TAGS_READ.read_text(encoding="utf-8"))
        parts.append(WRITE_PRELUDE.read_text(encoding="utf-8"))
    parts.append((SCRIPT_DIR / GUARD).read_text(encoding="utf-8"))
    if needs_helpers:
        parts.append((SCRIPT_DIR / WRITE_HELPERS).read_text(encoding="utf-8"))
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
def _tag(value: Any) -> str:
    tag = str(value or "")
    if not _TAG.match(tag):
        raise ValueError("tag is required: 1-80 printable ASCII characters (your label for this build phase)")
    return tag


def _ident(value: Any, what: str) -> str:
    text = str(value if value is not None else "")
    if not _IDENT.match(text):
        raise ValueError(f"{what} is required: 1-60 letters, digits, '_', '-' or '.'")
    return text


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


def _num(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{what} must be a finite number")
    return float(value)


def _positive(value: Any, what: str, upper: float) -> float:
    number = _num(value, what)
    if not 0 < number <= upper:
        raise ValueError(f"{what} must be greater than 0 and at most {upper:g}")
    return number


def _num_list(value: Any, what: str, size: int) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{what} must be a list of {size} numbers")
    return [_num(v, what) for v in value]


def _int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{what} must be an integer")
    return int(value)


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


class DomainMismatch(ValueError):
    """The requested system does not belong to the tool's kind (static part of the category guard)."""


def normalize_system(value: Any, kind: str, what: str = "system") -> str:
    """Revit system class name for a short key ('hsup') or a Revit name ('SupplyHydronic'); refuses another domain's system."""
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(f"{what} is required, for example {', '.join(REVIT_SYSTEMS[kind][:3])}")
    found: Optional[Tuple[str, str]] = SYSTEM_KEYS.get(text.lower())
    if found is None:
        for k, names in REVIT_SYSTEMS.items():
            for n in names:
                if n.lower() == text.lower():
                    found = (k, n)
    if found is None:
        known = ", ".join(REVIT_SYSTEMS[kind])
        raise ValueError(f"unknown {what} '{text}' for a {KIND_LABEL[kind]} tool; use one of {known} (or a short key: "
                         + ", ".join(k for k, v in SYSTEM_KEYS.items() if v[0] == kind) + ")")
    if found[0] != kind:
        raise DomainMismatch(
            f"{what} '{text}' is a {KIND_LABEL[found[0]]} system ({found[1]}) but this tool works on {KIND_LABEL[kind]} systems. "
            f"A family of the {KIND_LABEL[found[0]]} domain is never placed in a {KIND_LABEL[kind]} system."
        )
    return found[1]


def _size(value: Any, kind: str, what: str) -> Dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be an object: {{diameter_mm}} or, for a rectangular duct, {{width_mm, height_mm}}")
    unknown = set(value) - {"diameter_mm", "width_mm", "height_mm"}
    if unknown:
        raise ValueError(f"{what} has unknown keys: {', '.join(sorted(unknown))}")
    if value.get("diameter_mm") is not None:
        if value.get("width_mm") is not None or value.get("height_mm") is not None:
            raise ValueError(f"{what}: give diameter_mm or width_mm with height_mm, not both")
        return {"d": _positive(value["diameter_mm"], f"{what}.diameter_mm", 3000.0)}
    if value.get("width_mm") is not None and value.get("height_mm") is not None:
        if kind != "duct":
            raise ValueError(f"{what}: a pipe is round; give diameter_mm")
        return {"w": _positive(value["width_mm"], f"{what}.width_mm", 5000.0), "h": _positive(value["height_mm"], f"{what}.height_mm", 5000.0)}
    raise ValueError(f"{what} needs diameter_mm (or width_mm and height_mm for a rectangular duct)")


def _element_ref(value: Any, what: str) -> Dict[str, Any]:
    """{element_id} or {mark}, plus the optional connector filters; returns the cleaned dict."""
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be an object with element_id or mark")
    unknown = set(value) - {"element_id", "mark", "point_m", "diameter_mm", "sort", "index", "near_m"}
    if unknown:
        raise ValueError(f"{what} has unknown keys: {', '.join(sorted(unknown))}")
    out: Dict[str, Any] = {}
    given = [k for k in ("element_id", "mark") if value.get(k) not in (None, "")]
    if len(given) != 1:
        raise ValueError(f"{what} needs exactly one of element_id or mark")
    if given[0] == "element_id":
        out["element_id"] = _int(value["element_id"], f"{what}.element_id")
    else:
        mark = str(value["mark"])
        if len(mark) > 80 or any(ord(c) < 32 for c in mark):
            raise ValueError(f"{what}.mark must be 1-80 printable characters")
        out["mark"] = mark
    if value.get("diameter_mm") is not None:
        lo, hi = _num_list(value["diameter_mm"], f"{what}.diameter_mm", 2)
        if lo < 0 or hi < lo:
            raise ValueError(f"{what}.diameter_mm must be [low, high] with 0 <= low <= high")
        out["diameter_mm"] = [lo, hi]
    if value.get("sort") not in (None, ""):
        out["sort"] = _choice(value["sort"], ("x", "y", "z"), f"{what}.sort")
    if value.get("index") is not None:
        index = _int(value["index"], f"{what}.index")
        if index < 0:
            raise ValueError(f"{what}.index must be 0 or more")
        out["index"] = index
    if value.get("near_m") is not None:
        out["near_m"] = _num_list(value["near_m"], f"{what}.near_m", 3)
    return out


def _endpoint(value: Any, what: str) -> Dict[str, Any]:
    if isinstance(value, dict) and value.get("point_m") is not None:
        if any(value.get(k) not in (None, "") for k in ("element_id", "mark")):
            raise ValueError(f"{what}: give a connector (element_id or mark) or a point_m, not both")
        extra = set(value) - {"point_m"}
        if extra:
            raise ValueError(f"{what}: a point takes only point_m, not {', '.join(sorted(extra))}")
        return {"point_m": _num_list(value["point_m"], f"{what}.point_m", 3)}
    if isinstance(value, dict) and value.get("near_m") is not None:
        raise ValueError(f"{what}: near_m belongs to revit_mep_connect; a route picks its connector with diameter_mm, sort and index")
    return _element_ref(value, what)


def _spec_of(value: Any, what: str) -> Dict[str, Any]:
    """An element reference without connector filters (circuit members, panel, check_elements)."""
    ref = _element_ref(value, what)
    extra = set(ref) - {"element_id", "mark"}
    if extra:
        raise ValueError(f"{what}: connector filters ({', '.join(sorted(extra))}) do not apply here")
    return ref


def _on_error(value: Any) -> str:
    return _choice(value, ("abort", "skip"), "on_error", "abort")


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #
ITEM_TYPES = {
    "id": "int", "a_id": "int", "b_id": "int", "panel_id": "int", "elements": "int", "length_mm": "float",
}
SYSTEM_CHECK_NAME = "revit_system_report on the changed pipes, ducts and fittings"


def _finish_write(
    tool: str,
    parsed: ScriptOutput,
    elapsed: int,
    workspace: Any,
    *,
    extra: Optional[Dict[str, Any]] = None,
    extra_checks: Optional[List[Dict[str, Any]]] = None,
    unverified: Optional[str] = None,
) -> Dict[str, Any]:
    outcome = parsed.meta.get("outcome", "ok")
    changed = _ints(parsed.meta.get("changed_ids"))
    failed_ids = _ints(parsed.meta.get("failed_ids"))
    posts = [r for r in parsed.rows if r.get("row_type") == "post"]
    items = [{k: v for k, v in r.items() if k != "row_type"} for r in parsed.rows if r.get("row_type") == "item"]
    checks = [{"check": r.get("check"), "ok": r.get("ok") == "1", "detail": r.get("detail", "")} for r in posts]
    checks.extend(extra_checks or [])
    checks.sort(key=lambda c: c["ok"])  # failures first
    failed_checks = sum(1 for c in checks if not c["ok"])
    post_check = {"ok": failed_checks == 0, "checked": len(checks), "failed": failed_checks, "checks": checks[:40]}
    if outcome == "ok" and not post_check["ok"]:
        outcome = "post_check_failed"

    infos = list(parsed.infos)
    if unverified:
        infos.append("UNVERIFIED: " + unverified)
    synthetic = ScriptOutput(
        summary=parsed.summary,
        fails=list(parsed.fails),
        infos=infos,
        rows=items,
        meta=dict(parsed.meta),
        counts={"fail": parsed.counts.get("fail", len(parsed.fails)), "info": len(infos), "row": len(items)},
    )
    if unverified:
        synthetic.meta["verified"] = "0"
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
    failed_checks_text = [c for c in checks if not c["ok"]]
    if not ok:
        first = parsed.fails[0] if parsed.fails else (
            ("%s: %s" % (failed_checks_text[0]["check"], failed_checks_text[0]["detail"])) if failed_checks_text else outcome)
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
        if parsed.fails:
            result["message"] = parsed.fails[0]
        elif failed_checks_text:
            result["message"] = "%s: %s" % (failed_checks_text[0]["check"], failed_checks_text[0]["detail"])
        else:
            result["message"] = f"outcome: {outcome}"
        result["element_ids"] = failed_ids
        result["hint"] = _HINTS.get(result["kind"], "")
    return result


def _revit_module_class() -> Any:
    """The revit module's class (it owns revit_system_report). The registry may have loaded it as a plain module, so look
    in sys.modules first and fall back to loading the file."""
    mod = sys.modules.get("revit_mcp_server.modules.revit")
    cls = getattr(mod, "RevitModule", None)
    if cls is not None:
        return cls
    name = "revit_mcp_server.modules._revit_for_mep"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, REVIT_MODULE_DIR / "module.py")
        if spec is None or spec.loader is None:
            raise ImportError("cannot load the revit module")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod.RevitModule


def _system_check(
    ids: List[int],
    allow_open_ids: List[int],
    hard_codes: Tuple[str, ...],
    approved_executor: Optional[ToolExecutor],
    workspace: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    """Run revit_system_report (read-only, existing tool) on the created elements.

    Returns ``(checks, extra fields, unverified reason)``. A report that cannot run leaves the call unverified, never passed.
    """
    if not ids:
        return [], {}, None
    try:
        report = _revit_module_class()().system_report(
            ids=ids, allow_open_ids=allow_open_ids, max_elements=5000, time_budget_s=20.0, limit=500,
            workspace=workspace, tool_executor=approved_executor,
        )
    except Exception as exc:  # noqa: BLE001 - the model is already changed; say what could not be checked
        return [], {"system_report": {"ran": False, "reason": str(exc)}}, f"revit_system_report could not run ({exc})"
    if not isinstance(report, dict) or report.get("ok") is False:
        reason = (report or {}).get("message") if isinstance(report, dict) else "unexpected answer"
        return [], {"system_report": {"ran": False, "reason": str(reason)}}, f"revit_system_report could not run ({reason})"
    fails = [str(f) for f in report.get("fails", [])]
    total = int((report.get("limits") or {}).get("fails_total", len(fails)) or 0)
    hard = [f for f in fails if f.split(":", 1)[0].strip() in hard_codes]
    hidden = max(0, total - len(fails))
    soft = [f for f in fails if f.split(":", 1)[0].strip() not in hard_codes]
    detail = f"{len(hard)} problem(s) that count" if hard or hidden else "no open ends, disconnected fittings, flow or size mismatches"
    if hidden:
        detail += f"; {hidden} more report lines were not shown and are counted as problems"
    if hard:
        detail += ": " + "; ".join(hard[:3])
    check = {"check": SYSTEM_CHECK_NAME, "ok": not hard and not hidden, "detail": detail}
    open_rows = [r for r in report.get("rows", []) if r.get("kind") == "open_end"]
    extra = {
        "system_report": {
            "ran": True,
            "summary": report.get("summary"),
            "verified": bool(report.get("verified")),
            "problems_counted": len(hard) + hidden,
            "not_counted": soft[:20],
        },
        "open_ends": open_rows,
    }
    reason: Optional[str] = None
    if not report.get("verified") or (report.get("limits") or {}).get("partial"):
        reason = "revit_system_report was partial or could not measure everything: " + str(report.get("summary"))
    return [check], extra, reason


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
class RevitMepModule:

    # ---- read-only ---------------------------------------------------------- #
    def check_elements(
        self,
        kind: Any = None,
        system: Any = None,
        elements: Any = None,
        need_free: Any = False,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_mep_check_elements"
        try:
            k = _choice(kind, ("pipe", "duct", "elec"), "kind")
            args: Dict[str, Any] = {"kind": k, "system": "", "need_free": bool(need_free)}
            if system not in (None, ""):
                args["system"] = normalize_system(system, k)
            if not isinstance(elements, list) or not 1 <= len(elements) <= 200:
                raise ValueError("elements must be a list of 1 to 200 objects with element_id or mark")
            args["elements"] = [_spec_of(e, f"elements[{i}]") for i, e in enumerate(elements)]
        except DomainMismatch as exc:
            return error_result(tool, "domain_mismatch", str(exc), hint=_HINTS["domain_mismatch"])
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "check_elements.ipy", args, write=False, tool_executor=tool_executor, approved_executor=None)
        if early is not None or parsed is None:
            return early or {}
        result = assemble_result(
            tool,
            parsed,
            PageSpec(limit=200),
            row_types={"element_id": "int"},
            elapsed_ms=elapsed,
            workspace=workspace,
        )
        refused = [r for r in result.get("rows", []) if r.get("verdict") != "ok"]
        result["would_be_refused"] = len(refused)
        return result

    # ---- write -------------------------------------------------------------- #
    def route(
        self,
        kind: Any = None,
        tag: Any = None,
        system: Any = None,
        type_name: Any = None,
        system_type_name: Any = None,
        routes: Any = None,
        transition_m: Any = 0.15,
        on_error: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_mep_route"
        try:
            k = _choice(kind, ("pipe", "duct"), "kind")
            args: Dict[str, Any] = {
                "kind": k,
                "tag": _tag(tag),
                "system": normalize_system(system, k),
                "type_name": _name(type_name, "type_name") if type_name not in (None, "") else "",
                "system_type_name": _name(system_type_name, "system_type_name") if system_type_name not in (None, "") else "",
                "transition_m": _positive(transition_m if transition_m is not None else 0.15, "transition_m", 2.0),
                "on_error": _on_error(on_error),
            }
            if not isinstance(routes, list) or not 1 <= len(routes) <= 25:
                raise ValueError("routes must be a list of 1 to 25 routes")
            args["routes"] = [self._route(r, k, i, bool(args["type_name"])) for i, r in enumerate(routes)]
        except DomainMismatch as exc:
            return error_result(tool, "domain_mismatch", str(exc), hint=_HINTS["domain_mismatch"])
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        return self._write(tool, "route.ipy", args, workspace, approved_executor, hard_codes=ROUTE_HARD_CODES, report=True)

    @staticmethod
    def _route(r: Any, kind: str, index: int, has_default_type: bool) -> Dict[str, Any]:
        what = f"routes[{index}]"
        if not isinstance(r, dict):
            raise ValueError(f"{what} must be an object")
        unknown = set(r) - {"id", "level", "run_height_m", "size", "stub_m", "type_name", "from", "to", "branch_to", "via"}
        if unknown:
            raise ValueError(f"{what} has unknown keys: {', '.join(sorted(unknown))}")
        out: Dict[str, Any] = {"id": _ident(r.get("id"), f"{what}.id"), "level": _name(r.get("level"), f"{what}.level")}
        tname = r.get("type_name")
        if tname not in (None, ""):
            out["type_name"] = _name(tname, f"{what}.type_name")
        elif not has_default_type:
            raise ValueError(f"{what}: give type_name on the route or on the call (the {kind} type to use)")
        out["size"] = _size(r.get("size"), kind, f"{what}.size")
        stub = r.get("stub_m", 0.2)
        stub_m = _num(0.2 if stub is None else stub, f"{what}.stub_m")
        if not 0 <= stub_m <= 3:
            raise ValueError(f"{what}.stub_m must be between 0 and 3 metres")
        out["stub_m"] = stub_m
        if r.get("from") is None:
            raise ValueError(f"{what}.from is required: a connector (element_id or mark) or a point_m")
        out["from"] = _endpoint(r["from"], f"{what}.from")
        if (r.get("to") is None) == (r.get("branch_to") is None):
            raise ValueError(f"{what}: give exactly one of to (another connector or point) or branch_to (a trunk)")
        if r.get("to") is not None:
            out["to"] = _endpoint(r["to"], f"{what}.to")
        else:
            bt = r["branch_to"]
            if not isinstance(bt, dict) or set(bt) - {"route", "element_ids", "fitting"}:
                raise ValueError(f"{what}.branch_to must be an object with route or element_ids, and optionally fitting")
            if (bt.get("route") in (None, "")) == (not bt.get("element_ids")):
                raise ValueError(f"{what}.branch_to needs exactly one of route or element_ids")
            clean_bt: Dict[str, Any] = {"fitting": _choice(bt.get("fitting"), ("takeoff", "tee"), f"{what}.branch_to.fitting", "takeoff")}
            if bt.get("route") not in (None, ""):
                clean_bt["route"] = _ident(bt["route"], f"{what}.branch_to.route")
            else:
                ids = bt["element_ids"]
                if not isinstance(ids, list) or not 1 <= len(ids) <= 50:
                    raise ValueError(f"{what}.branch_to.element_ids must be 1 to 50 ids")
                clean_bt["element_ids"] = [_int(i, f"{what}.branch_to.element_ids") for i in ids]
            out["branch_to"] = clean_bt
            if r.get("via"):
                raise ValueError(f"{what}: a branch has no via points")
        if out.get("branch_to"):
            run_height = r.get("run_height_m")
            if run_height is not None:
                raise ValueError(f"{what}: a branch runs at the height of its trunk; leave run_height_m out")
            out["run_height_m"] = 0.0
        else:
            if r.get("run_height_m") is None:
                raise ValueError(f"{what}.run_height_m is required: the height of the horizontal run above the level, in metres")
            out["run_height_m"] = _num(r["run_height_m"], f"{what}.run_height_m")
        via_in = r.get("via") or []
        if not isinstance(via_in, list) or len(via_in) > 20:
            raise ValueError(f"{what}.via must be a list of at most 20 points")
        via: List[Dict[str, Any]] = []
        for j, v in enumerate(via_in):
            vw = f"{what}.via[{j}]"
            if not isinstance(v, dict) or set(v) - {"x_m", "y_m", "to_height_m", "level", "size"}:
                raise ValueError(f"{vw} must be an object with x_m, y_m and optionally to_height_m, level, size")
            entry: Dict[str, Any] = {"x_m": _num(v.get("x_m"), f"{vw}.x_m"), "y_m": _num(v.get("y_m"), f"{vw}.y_m")}
            if v.get("to_height_m") is not None:
                entry["to_height_m"] = _num(v["to_height_m"], f"{vw}.to_height_m")
            if v.get("level") not in (None, ""):
                entry["level"] = _name(v["level"], f"{vw}.level")
            if v.get("size") is not None:
                entry["size"] = _size(v["size"], kind, f"{vw}.size")
            via.append(entry)
        out["via"] = via
        return out

    def connect(
        self,
        kind: Any = None,
        tag: Any = None,
        system: Any = None,
        connections: Any = None,
        tolerance_mm: Any = 5.0,
        on_error: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_mep_connect"
        try:
            k = _choice(kind, ("pipe", "duct"), "kind")
            args: Dict[str, Any] = {
                "kind": k,
                "tag": _tag(tag),
                "system": normalize_system(system, k),
                "tolerance_mm": _positive(tolerance_mm if tolerance_mm is not None else 5.0, "tolerance_mm", 50.0),
                "on_error": _on_error(on_error),
            }
            if not isinstance(connections, list) or not 1 <= len(connections) <= 50:
                raise ValueError("connections must be a list of 1 to 50 connections")
            clean: List[Dict[str, Any]] = []
            for i, c in enumerate(connections):
                what = f"connections[{i}]"
                if not isinstance(c, dict) or set(c) - {"id", "a", "b", "joint"}:
                    raise ValueError(f"{what} must be an object with id, a, b and optionally joint")
                if c.get("a") is None or c.get("b") is None:
                    raise ValueError(f"{what} needs a and b (element_id or mark, with optional connector filters)")
                clean.append({
                    "id": _ident(c.get("id"), f"{what}.id"),
                    "a": _element_ref(c["a"], f"{what}.a"),
                    "b": _element_ref(c["b"], f"{what}.b"),
                    "joint": _choice(c.get("joint"), ("auto", "direct", "elbow", "union", "transition"), f"{what}.joint", "auto"),
                })
            args["connections"] = clean
        except DomainMismatch as exc:
            return error_result(tool, "domain_mismatch", str(exc), hint=_HINTS["domain_mismatch"])
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        return self._write(tool, "connect.ipy", args, workspace, approved_executor, hard_codes=CONNECT_HARD_CODES, report=True)

    def circuit(
        self,
        tag: Any = None,
        system: Any = "power",
        circuits: Any = None,
        on_error: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_mep_circuit"
        try:
            args: Dict[str, Any] = {
                "tag": _tag(tag),
                "system": normalize_system(system if system not in (None, "") else "power", "elec"),
                "on_error": _on_error(on_error),
            }
            if not isinstance(circuits, list) or not 1 <= len(circuits) <= 50:
                raise ValueError("circuits must be a list of 1 to 50 circuits")
            clean: List[Dict[str, Any]] = []
            for i, c in enumerate(circuits):
                what = f"circuits[{i}]"
                if not isinstance(c, dict) or set(c) - {"id", "name", "panel", "elements"}:
                    raise ValueError(f"{what} must be an object with id, panel, elements and optionally name")
                if c.get("panel") is None:
                    raise ValueError(f"{what}.panel is required (element_id or mark of the panel)")
                members = c.get("elements")
                if not isinstance(members, list) or not 1 <= len(members) <= 200:
                    raise ValueError(f"{what}.elements must be a list of 1 to 200 element references")
                entry: Dict[str, Any] = {
                    "id": _ident(c.get("id"), f"{what}.id"),
                    "panel": _spec_of(c["panel"], f"{what}.panel"),
                    "elements": [_spec_of(m, f"{what}.elements[{j}]") for j, m in enumerate(members)],
                }
                if c.get("name") not in (None, ""):
                    entry["name"] = _name(c["name"], f"{what}.name")
                clean.append(entry)
            args["circuits"] = clean
        except DomainMismatch as exc:
            return error_result(tool, "domain_mismatch", str(exc), hint=_HINTS["domain_mismatch"])
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        return self._write(tool, "circuit.ipy", args, workspace, approved_executor, hard_codes=(), report=False)

    # ---- shared write path -------------------------------------------------- #
    def _write(
        self,
        tool: str,
        script_name: str,
        args: Dict[str, Any],
        workspace: Any,
        approved_executor: Optional[ToolExecutor],
        *,
        hard_codes: Tuple[str, ...],
        report: bool,
    ) -> Dict[str, Any]:
        parsed, elapsed, early = _run(tool, script_name, args, write=True, tool_executor=None, approved_executor=approved_executor)
        if early is not None or parsed is None:
            return early or {}
        checks: List[Dict[str, Any]] = []
        extra: Dict[str, Any] = {}
        unverified: Optional[str] = None
        if report and parsed.meta.get("outcome", "ok") == "ok":
            ids = _ints(parsed.meta.get("changed_ids") if script_name == "route.ipy" else parsed.meta.get("report_ids"))
            allow = _ints(parsed.meta.get("free_end_ids"))
            checks, extra, unverified = _system_check(ids, allow, hard_codes, approved_executor, workspace)
        return _finish_write(tool, parsed, elapsed, workspace, extra=extra, extra_checks=checks, unverified=unverified)


# Codes of revit_system_report that make a call fail. Equipment ports that stay unconnected and separate groups of
# members are normal after a partial build, so they are listed but never fail a call.
ROUTE_HARD_CODES = ("SYS_OPEN_END", "SYS_FITTING_DISCONNECTED", "SYS_FLOW_MISMATCH", "SYS_SIZE_MISMATCH")
CONNECT_HARD_CODES = ("SYS_FITTING_DISCONNECTED", "SYS_FLOW_MISMATCH", "SYS_SIZE_MISMATCH")
