"""
revit_sparing module - sparingen (openings where MEP passes through walls and floors) for a live Revit session.

Dutch contractor BIM teams model every penetration as a sparing: an opening family or a native opening with an
approval status, later copied into the discipline models (BIM Loket "Workflow sparingscoordinatie"). This module covers
that workflow.

Commands (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  find            read-only  where do ducts, pipes, conduits and cable trays cross walls, floors (and optionally roofs and
                             structural framing), in the active model and optionally in linked models; per crossing the size
                             of the MEP element, the host thickness, the passage angle, whether an opening is already there,
                             and a suggested sparing size (MEP size + clearance per side, rounded up)
  place           WRITE      place sparings at those crossings: an existing loaded sparing family ('family') or a native
                             opening ('opening'), sized, tagged and given a status
  status_get      read-only  the approval status of each sparing, with discipline, level and host
  status_summary  read-only  counts grouped by status, discipline, level, host category, family, tag or kind
  status_set      WRITE      move sparings along the status table; the whole call is refused on an illegal move
  status_setup    WRITE      create the status parameter (shared parameter) and bind it; the documented, approval-gated step
  export_spec     read-only  the placement spec (JSON) for the linked discipline models, in the links' own coordinates
  place_spec      WRITE      place sparings in the ACTIVE document from such a spec (idempotent, dry_run)

Approval status. Each sparing carries one text instance parameter (default name 'Sparing status'). The five statuses are
proposed, requested, approved, rejected, built, stored as Voorstel, Aangevraagd, Akkoord, Afgewezen, Gebouwd (replaceable
per call with status_labels). Allowed moves: proposed > requested; requested > approved or rejected; approved > built or
rejected; rejected > proposed; built is final; an empty status can only become proposed. status_set checks every target
first and refuses the whole call, changing nothing, for an illegal move, a stored text that is none of the labels, or a
sparing without a writable text parameter; then it sets each value in its own transaction and reads it back. If the
parameter does not exist the read tools report it (status no_parameter, a 'setup' note in the result) and nothing is
created. Creating it is a separate, documented step that only runs when someone approves a plan for status_setup: it adds
a definition to the shared parameter file (a rollback cannot undo that file write) and binds it as an instance parameter
to the chosen categories (default Generic Models); dry_run writes nothing. Not tracked: who changed a status and when.

Copying to the discipline models. The host model's sparingen are placed against hosts that often live in links (the
architect's walls, the structural floors). export_spec groups the host model's sparingen by the link that holds their host
(read from the crossing id the sparing carries, for example 340xL700.101 = pipe 340 through wall 101 of link instance 700)
and turns each location and direction into that link's own internal coordinates with the inverse of
RevitLinkInstance.GetTotalTransform. place_spec places them from such a spec. The bridge works on the ACTIVE document
only, so writing into a discipline model needs that model to be the active document when place_spec runs: open it, make it
active, call the tool. place_spec compares the active document with the one the spec was made for (creation GUID, or title
with a workshared user suffix) and refuses on a mismatch unless skip_document_check is set. Hosts are found by element id
in the active document; a missing host refuses the call (on_error=skip places the rest). Sparings are tagged like
revit_sparing_place, so a re-run with the same tag replaces only what it made.

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

Follow-ups (not built yet): who and when for each status change (an audit trail), an IFC or BCF hand-off of the
proposals, sparing families per shape (round core drill vs rectangular), bundling several runs into one sparing, sloped
floors and roofs (the frame assumes a horizontal floor), curved MEP runs and curved walls in the native opening mode,
exporting specs for sparingen whose hosts are in this model (copy to a second host model) and syncing status back from the
discipline model.

UNVERIFIED: nothing here has run against a live Revit. The scripts are syntax-checked and exercised against a stub of
the Revit API (tests/revit_sparing_stub.py on top of revit_api_stub.py and revit_mep_stub.py), which proves the
control flow, the arithmetic, the budgets, ownership/replace rules, rollback and the line protocol, not that Revit
accepts the calls. Also unproven for the status and spec tools: LookupParameter and Parameter.Set on text parameters of family instances and
openings, doc.ParameterBindings iteration, Insert and ReInsert with a ForgeTypeId group (GroupTypeId.IdentityData),
Application.OpenSharedParameterFile, ExternalDefinitionCreationOptions with SpecTypeId.String.Text, writing the shared
parameter file, CategorySet and InstanceBinding creation, Category.AllowsBoundParameters, reading FamilyInstance.Host and
Symbol.Family, Document.CreationGUID of a workshared local copy against its central model, RevitLinkInstance link
transforms (BasisX, Origin, Inverse) on a rotated link, Wall.Orientation of linked walls, and the face-based placement
against a host face picked from the exported position in the discipline model.
Specifically unproven in a live model: Solid.IntersectWithCurve on wall and floor solids,
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
SCRIPTS: Dict[str, bool] = {
    "find.ipy": False, "place.ipy": True, "status_get.ipy": False, "status_set.ipy": True, "status_setup.ipy": True,
    "export_spec.ipy": False, "place_spec.ipy": True,
}
# Shared source files loaded between the preludes and ARGS, per script (order matters). Every file holds definitions only.
STATUS_LIB = "_sparing_status.ipy"
PLACE_LIB = "_sparing_place_lib.ipy"
SCRIPT_PARTS: Dict[str, Tuple[str, ...]] = {
    "find.ipy": (DETECT,),
    "place.ipy": (DETECT, PLACE_LIB),
    "status_get.ipy": (STATUS_LIB,),
    "status_set.ipy": (STATUS_LIB,),
    "status_setup.ipy": (STATUS_LIB,),
    "export_spec.ipy": (DETECT, STATUS_LIB),
    "place_spec.ipy": (DETECT, STATUS_LIB, PLACE_LIB),
}
# Scripts that read Extensible Storage tags even though they do not write.
READS_TAGS = ("status_get.ipy", "export_spec.ipy")

MEP_CATEGORIES = ("pipes", "ducts", "conduits", "cabletrays")
HOST_CATEGORIES = ("walls", "floors", "roofs", "structuralframing")
_CATEGORY_ALIASES = {
    "pipe": "pipes", "pipes": "pipes", "duct": "ducts", "ducts": "ducts", "conduit": "conduits", "conduits": "conduits",
    "cabletray": "cabletrays", "cabletrays": "cabletrays", "wall": "walls", "walls": "walls", "floor": "floors",
    "floors": "floors", "roof": "roofs", "roofs": "roofs", "structuralframing": "structuralframing",
    "framing": "structuralframing", "beams": "structuralframing", "beam": "structuralframing",
}
SIZE_KEYS = ("width", "height", "depth", "diameter")

# Approval status of a sparing, stored as text in one instance parameter. The keys are English; the stored text is the label
# (Dutch by default) and can be replaced per call with status_labels. Moves not in this table are refused.
STATUS_KEYS = ("proposed", "requested", "approved", "rejected", "built")
STATUS_EXTRA = ("unset", "unknown", "no_parameter", "unwritable")  # what a read can report besides the five statuses
DEFAULT_LABELS = {"proposed": "Voorstel", "requested": "Aangevraagd", "approved": "Akkoord", "rejected": "Afgewezen", "built": "Gebouwd"}
TRANSITIONS: Dict[str, List[str]] = {
    "proposed": ["requested"],
    "requested": ["approved", "rejected"],
    "approved": ["built", "rejected"],
    "rejected": ["proposed"],
    "built": [],
}
FROM_UNSET = ["proposed"]  # a sparing with an empty status can only start as proposed
DEFAULT_STATUS_PARAMETER = "Sparing status"
DEFAULT_GROUP = "AEC Sparing"
GROUP_FIELDS = {"status": "status", "discipline": "discipline", "level": "level", "host_category": "host_cat", "family": "family",
                "tag": "tag", "kind": "kind"}
SETUP_CATEGORIES = {
    "genericmodels": "OST_GenericModel", "specialtyequipment": "OST_SpecialityEquipment", "mechanicalequipment": "OST_MechanicalEquipment",
    "wallopenings": "OST_SWallRectOpening", "flooropenings": "OST_FloorOpening", "shaftopenings": "OST_ShaftOpening",
}

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
    "element_not_found": "Use element ids from revit_sparing_status_get in the active document. Nothing was changed.",
    "illegal_transition": "Nothing was changed. The allowed moves are in the result's transitions table: proposed > requested > approved or rejected; approved > built or rejected; rejected > proposed. Move step by step.",
    "shared_parameter_file_missing": "Point Revit at the firm's shared parameter file (Manage > Shared Parameters) or pass shared_parameter_file, then call again. Nothing was changed.",
    "no_bindable_category": "Pick categories that allow bound parameters (genericmodels, specialtyequipment ...). Nothing was changed.",
    "bindings_unreadable": "Revit would not list the project's parameter bindings; nothing was changed. Check revit_health and try again.",
    "wrong_document": "The bridge works on the active document only. Open the discipline model named in the message, make it the active document, and call again. Nothing was changed.",
    "host_not_found": "The spec names hosts by element id; they must exist in the active document. Check you are in the right model, or use on_error=skip to place the rest. Nothing was changed.",
    "link_not_found": "force_link_id must be a loaded link instance (see the links in the spec). Nothing was changed.",
    "dry_run_not_honoured": "A dry run was asked for but the script reports a commit. Check the model with revit_warnings_delta before doing anything else.",
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
    totals: Optional[Dict[str, Any]] = None,
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
    return _summary_first(result, totals if totals is not None else _totals(parsed.meta))


# --------------------------------------------------------------------------- #
# Approval status helpers (revit_sparing_status_*)
# --------------------------------------------------------------------------- #
def _opt_tag(value: Any) -> str:
    return "" if value in (None, "") else _tag(value)


def _labels(value: Any) -> Dict[str, str]:
    """The stored text per status key: the defaults with the caller's replacements."""
    labels = dict(DEFAULT_LABELS)
    if value in (None, {}):
        return labels
    if not isinstance(value, dict):
        raise ValueError('status_labels must be an object such as {"approved": "Goedgekeurd"}')
    unknown = set(value) - set(STATUS_KEYS)
    if unknown:
        raise ValueError(f"status_labels has unknown keys: {', '.join(sorted(unknown))}; use {', '.join(STATUS_KEYS)}")
    for key, text in value.items():
        labels[key] = _name(text, f"status_labels.{key}")
    lows = [v.lower() for v in labels.values()]
    if len(set(lows)) != len(lows):
        raise ValueError("status_labels must differ from each other (case does not count)")
    for key, text in labels.items():
        if text.lower() in STATUS_KEYS and text.lower() != key:
            raise ValueError(f"status_labels.{key}: the text {text!r} is the key of another status; use another text")
    return labels


def _status_key(value: Any, labels: Dict[str, str], what: str) -> str:
    low = str(value if value is not None else "").strip().lower()
    if low in STATUS_KEYS:
        return low
    for key, text in labels.items():
        if text.lower() == low:
            return key
    raise ValueError(f"{what}: unknown status {value!r}; use one of {', '.join(STATUS_KEYS)} (or their stored texts: {', '.join(labels.values())})")


def _status_words(value: Any, labels: Dict[str, str], what: str) -> List[str]:
    if value in (None, []):
        return []
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError(f"{what} must be a list of statuses: {', '.join(STATUS_KEYS + STATUS_EXTRA)}")
    out: List[str] = []
    for v in value:
        low = str(v).strip().lower()
        word = low if low in STATUS_EXTRA else _status_key(v, labels, what)
        if word not in out:
            out.append(word)
    return out


def _status_parameter(value: Any) -> str:
    return _name(value if value not in (None, "") else DEFAULT_STATUS_PARAMETER, "status_parameter")


def _selection(tag: Any, family_name: Any, ids: Any) -> Dict[str, Any]:
    clean: List[int] = []
    if ids not in (None, []):
        if not isinstance(ids, list) or len(ids) > 2000:
            raise ValueError("ids must be a list of at most 2000 element ids")
        for i in ids:
            clean.append(_int(i, "ids", 1, 2**62, 0))
        if len(set(clean)) != len(clean):
            raise ValueError("ids lists the same element twice")
    return {"tag": _opt_tag(tag), "family_name": _opt_name(family_name, "family_name"), "ids": clean}


def _status_row_types() -> Dict[str, str]:
    return {"id": "int", "host_id": "int", "host_link": "int", "has_param": "bool", "writable": "bool"}


def _status_counts(rows: List[Dict[str, str]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        word = r.get("status", "")
        out[word] = out.get(word, 0) + 1
    return {k: out[k] for k in sorted(out, key=_status_order)}


def _status_order(word: str) -> Tuple[int, str]:
    order = STATUS_KEYS + STATUS_EXTRA
    return (order.index(word) if word in order else len(order), word)


def _status_meta_totals(meta: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ("selected", "shown", "with_param", "without_param", "unset", "unknown", "filtered_out"):
        try:
            out[key] = int(meta.get(key, "0") or 0)
        except ValueError:
            out[key] = 0
    out["truncated"] = meta.get("truncated", "0") == "1"
    return out


def _setup_note(meta: Dict[str, str], name: str) -> Optional[Dict[str, Any]]:
    """Honest report of a missing status parameter, with the documented next step. Nothing is created by a read."""
    try:
        missing = int(meta.get("without_param", "0") or 0)
    except ValueError:
        missing = 0
    bound = meta.get("parameter_bound", "")
    if not missing:
        return None
    note: Dict[str, Any] = {
        "needed": True,
        "parameter": name,
        "sparingen_without_parameter": missing,
        "exists_in_project": None if bound == "" else bound == "1",
        "bound_to_categories": [c for c in meta.get("parameter_categories", "").split(",") if c],
        "next_step": (
            "The status is stored in the text parameter '%s'. It is missing on %d sparingen. Nothing was created. To create it, call "
            "revit_sparing_status_setup (approval-gated, dry_run available): it adds a shared parameter and binds it to the sparing "
            "categories. Or add the parameter to the sparing family yourself." % (name, missing)
        ),
    }
    return note


def _group_rows(rows: List[Dict[str, str]], group_by: List[str]) -> List[Dict[str, Any]]:
    """One row per distinct combination of the group_by fields, with its count."""
    counts: Dict[Tuple[str, ...], int] = {}
    for r in rows:
        key = tuple(r.get(GROUP_FIELDS[g], "") or "(none)" for g in group_by)
        counts[key] = counts.get(key, 0) + 1

    def order(key: Tuple[str, ...]) -> Tuple[Any, ...]:
        return tuple(_status_order(v) if g == "status" else (0, v) for g, v in zip(group_by, key))

    return [{**dict(zip(group_by, key)), "count": counts[key]} for key in sorted(counts, key=order)]


def _group_by(value: Any) -> List[str]:
    if value in (None, []):
        return ["status"]
    if not isinstance(value, list) or len(value) > 4:
        raise ValueError(f"group_by must be a list of at most 4 of: {', '.join(GROUP_FIELDS)}")
    out: List[str] = []
    for v in value:
        key = str(v).strip().lower().replace(" ", "_")
        if key not in GROUP_FIELDS:
            raise ValueError(f"group_by: unknown field {v!r}; use {', '.join(GROUP_FIELDS)}")
        if key not in out:
            out.append(key)
    return out


def _setup_categories(value: Any) -> List[str]:
    if value in (None, []):
        return ["genericmodels"]
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError(f"categories must be a list of: {', '.join(SETUP_CATEGORIES)}")
    out: List[str] = []
    for v in value:
        key = str(v).strip().lower().replace(" ", "").replace("_", "")
        if key not in SETUP_CATEGORIES:
            raise ValueError(f"categories: unknown category {v!r}; use {', '.join(SETUP_CATEGORIES)}")
        if key not in out:
            out.append(key)
    return out


# --------------------------------------------------------------------------- #
# Spec helpers (revit_sparing_export_spec / revit_sparing_place_spec)
# --------------------------------------------------------------------------- #
SPEC_VERSION = 1
ACTIVE_DOCUMENT_NOTE = (
    "revit_sparing_place_spec writes into the ACTIVE document only. To place these sparingen in a discipline model, open that "
    "model, make it the active document, then call it. The bridge cannot write into a different open document."
)


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value) if str(value).strip() != "" else None
    except ValueError:
        return None


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(str(value)) if str(value).strip() != "" else None
    except ValueError:
        return None


def build_spec(parsed: ScriptOutput, labels: Dict[str, str], size_parameters: Dict[str, str]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """The spec (JSON-ready) and the sparingen that went to no link, from the rows of export_spec.ipy."""
    links: Dict[int, Dict[str, Any]] = {}
    unassigned: List[Dict[str, str]] = []
    for r in parsed.rows:
        kind = r.get("row_type")
        if kind == "link":
            lid = int(r["link_id"])
            links[lid] = {
                "link_instance_id": lid,
                "link_name": r.get("link_name", ""),
                "document_title": r.get("doc_title", ""),
                "document_guid": r.get("doc_guid", ""),
                "transform": {
                    "origin_mm": [_float_or_none(r.get(k)) for k in ("ox_mm", "oy_mm", "oz_mm")],
                    "rotation_deg_z": _float_or_none(r.get("rot_deg")),
                    "mirrored": r.get("mirrored") == "1",
                    "note": "link to host: point_in_host = rotate(point_in_link) + origin; locations below are already in the link's own coordinates",
                },
                "items": [],
            }
        elif kind == "unassigned":
            unassigned.append({k: v for k, v in r.items() if k != "row_type"})
    for r in parsed.rows:
        if r.get("row_type") != "item":
            continue
        status = r.get("status", "")
        item: Dict[str, Any] = {
            "key": r.get("key", ""),
            "source_id": _int_or_none(r.get("source_id")),
            "source_tag": r.get("source_tag", ""),
            "kind": r.get("kind", "family"),
            "family_name": r.get("family", ""),
            "type_name": r.get("type", ""),
            "host_id": _int_or_none(r.get("host_id")),
            "host_category": r.get("host_cat", ""),
            "level": r.get("level", ""),
            "discipline": r.get("discipline", ""),
            "status": status,
            "status_label": labels.get(status, ""),
            "location_mm": [_float_or_none(r.get(k)) for k in ("x_mm", "y_mm", "z_mm")],
            "normal": [_float_or_none(r.get(k)) for k in ("nx", "ny", "nz")],
            "normal_from": r.get("normal_from", ""),
            "host_model_location_mm": [_float_or_none(r.get(k)) for k in ("hx_mm", "hy_mm", "hz_mm")],
            "size_mm": {"width": _float_or_none(r.get("w_mm")), "height": _float_or_none(r.get("h_mm")),
                        "depth": _float_or_none(r.get("d_mm")), "shape": r.get("shape", ""), "from": r.get("size_from", "")},
        }
        links[int(r["link_id"])]["items"].append(item)
    spec: Dict[str, Any] = {
        "spec_version": SPEC_VERSION,
        "units": "mm",
        "coordinates": "internal coordinates of the linked document (location_mm, normal); host_model_location_mm is in the exporting model",
        "source": {"document": parsed.meta.get("doc_title"), "guid": parsed.meta.get("doc_guid"), "revit_version": parsed.meta.get("revit_version")},
        "status_labels": labels,
        "size_parameters": size_parameters,
        "links": [links[k] for k in sorted(links)],
    }
    return spec, unassigned


def _vec3(value: Any, what: str) -> List[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{what} must be a list of three numbers")
    out: List[float] = []
    for v in value:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or abs(float(v)) > 1e7:
            raise ValueError(f"{what} must hold finite numbers")
        out.append(float(v))
    return out


def _spec_item(index: int, raw: Any, labels: Dict[str, str], copy_status: bool) -> Dict[str, Any]:
    where = f"spec item {index}"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} is not an object")
    key = raw.get("key")
    if not isinstance(key, str) or not _CROSSING_ID.match(key):
        raise ValueError(f"{where}: key {key!r} is missing or not a crossing id (letters, digits and . # x -)")
    where = f"spec item {index} ({key})"
    loc = _vec3(raw.get("location_mm"), f"{where}: location_mm")
    normal = _vec3(raw.get("normal"), f"{where}: normal")
    if math.sqrt(sum(c * c for c in normal)) < 1e-6:
        raise ValueError(f"{where}: normal is a zero vector")
    size = raw.get("size_mm")
    if not isinstance(size, dict):
        raise ValueError(f"{where}: size_mm is missing")
    w = _num(size.get("width"), f"{where}: size_mm.width", 1.0, 20000.0, -1.0)
    h = _num(size.get("height"), f"{where}: size_mm.height", 1.0, 20000.0, -1.0)
    if w < 0 or h < 0:
        raise ValueError(f"{where}: size_mm needs width and height")
    d = None if size.get("depth") is None else _num(size.get("depth"), f"{where}: size_mm.depth", 0.0, 20000.0, 0.0)
    shape = size.get("shape") or "rect"
    if shape not in ("round", "rect"):
        raise ValueError(f"{where}: size_mm.shape must be round or rect")
    host_id = raw.get("host_id")
    if host_id is not None:
        host_id = _int(host_id, f"{where}: host_id", 1, 2**62, 1)
    host_cat = raw.get("host_category") or ""
    if host_cat and host_cat not in HOST_CATEGORIES:
        raise ValueError(f"{where}: host_category {host_cat!r} is none of {', '.join(HOST_CATEGORIES)}")
    kind = raw.get("kind") or ""
    if kind not in ("", "family", "opening"):
        raise ValueError(f"{where}: kind must be family or opening")
    status = str(raw.get("status") or "")
    return {
        "key": key, "source_id": raw.get("source_id") if isinstance(raw.get("source_id"), int) else 0, "kind": kind,
        "family_name": str(raw.get("family_name") or ""), "type_name": str(raw.get("type_name") or ""),
        "host_id": host_id, "host_cat": host_cat, "x_mm": loc[0], "y_mm": loc[1], "z_mm": loc[2],
        "nx": normal[0], "ny": normal[1], "nz": normal[2], "w_mm": w, "h_mm": h, "d_mm": d, "shape": shape,
        "status": status if (copy_status and status in labels) else "",
    }


def _spec_link(data: Any, link_instance_id: Any) -> Dict[str, Any]:
    if not isinstance(data, dict) or data.get("spec_version") != SPEC_VERSION:
        raise ValueError(f"the spec must be an object made by revit_sparing_export_spec (spec_version {SPEC_VERSION})")
    links = data.get("links")
    if not isinstance(links, list) or not links or not all(isinstance(x, dict) for x in links):
        raise ValueError("the spec has no links to place from")
    if link_instance_id is not None:
        want = _int(link_instance_id, "link_instance_id", 1, 2**62, 1)
        found = [x for x in links if x.get("link_instance_id") == want]
        if not found:
            raise ValueError(f"link_instance_id {want} is not in the spec; it has: {', '.join(str(x.get('link_instance_id')) for x in links)}")
        return found[0]
    if len(links) > 1:
        names = "; ".join(f"{x.get('link_instance_id')} = {x.get('link_name')}" for x in links[:10])
        raise ValueError(f"the spec has {len(links)} links; pass link_instance_id to choose one: {names}")
    return links[0]


def _safe_save_name(value: Any) -> str:
    if value in (None, ""):
        return ""
    if not is_safe_name(str(value)):
        raise ValueError("save_as must be a plain name: letters, digits, - and _, at most 64 characters")
    return str(value)


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

    # ---- approval status ---------------------------------------------------- #
    @staticmethod
    def _status_read_args(tag: Any, family_name: Any, ids: Any, status_parameter: Any, status_labels: Any,
                          discipline_parameter: Any, only_status: Any, max_elements: Any) -> Tuple[Dict[str, Any], Dict[str, str]]:
        labels = _labels(status_labels)
        args: Dict[str, Any] = _selection(tag, family_name, ids)
        args.update({
            "status_parameter": _status_parameter(status_parameter),
            "labels": labels,
            "discipline_parameter": _opt_name(discipline_parameter, "discipline_parameter"),
            "only_status": _status_words(only_status, labels, "only_status"),
            "max_elements": _int(max_elements, "max_elements", 1, 5000, 2000),
        })
        return args, labels

    def status_get(
        self,
        tag: Any = None,
        family_name: Any = None,
        ids: Any = None,
        status_parameter: Any = None,
        status_labels: Any = None,
        discipline_parameter: Any = None,
        only_status: Any = None,
        max_elements: Any = None,
        limit: Any = None,
        offset: Any = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_status_get"
        try:
            args, labels = self._status_read_args(tag, family_name, ids, status_parameter, status_labels, discipline_parameter, only_status, max_elements)
            page = PageSpec(limit=_int(limit, "limit", 1, MAX_LIMIT, 200), offset=_int(offset, "offset", 0, 10**7, 0))
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "status_get.ipy", args, write=False, tool_executor=tool_executor, approved_executor=None)
        if early is not None or parsed is None:
            return early or {}
        result = assemble_result(tool, parsed, page, row_types=_status_row_types(), elapsed_ms=elapsed, workspace=workspace)
        totals = _status_meta_totals(parsed.meta)
        totals["by_status"] = _status_counts(parsed.rows)
        result["status_parameter"] = args["status_parameter"]
        result["status_labels"] = labels
        result["transitions"] = TRANSITIONS
        note = _setup_note(parsed.meta, args["status_parameter"])
        if note:
            result["setup"] = note
        if totals["truncated"]:
            result["limits"]["truncated"] = True
            result["limits"]["partial"] = True
        return _summary_first(result, totals)

    def status_summary(
        self,
        group_by: Any = None,
        tag: Any = None,
        family_name: Any = None,
        ids: Any = None,
        status_parameter: Any = None,
        status_labels: Any = None,
        discipline_parameter: Any = None,
        max_elements: Any = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_status_summary"
        try:
            args, labels = self._status_read_args(tag, family_name, ids, status_parameter, status_labels, discipline_parameter, None, max_elements)
            groups = _group_by(group_by)
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "status_get.ipy", args, write=False, tool_executor=tool_executor, approved_executor=None)
        if early is not None or parsed is None:
            return early or {}
        grouped = _group_rows(parsed.rows, groups)
        synthetic = ScriptOutput(
            summary="%d sparingen in %d groups by %s" % (len(parsed.rows), len(grouped), ", ".join(groups)),
            fails=list(parsed.fails),
            infos=list(parsed.infos),
            rows=[{k: str(v) for k, v in g.items()} for g in grouped],
            meta=dict(parsed.meta),
            counts={"fail": parsed.counts.get("fail", len(parsed.fails)), "info": parsed.counts.get("info", len(parsed.infos)), "row": len(grouped)},
        )
        result = assemble_result(tool, synthetic, PageSpec(limit=MAX_LIMIT), row_types={"count": "int"}, elapsed_ms=elapsed, workspace=workspace)
        totals = _status_meta_totals(parsed.meta)
        totals["by_status"] = _status_counts(parsed.rows)
        totals["group_by"] = groups
        result["status_parameter"] = args["status_parameter"]
        result["status_labels"] = labels
        note = _setup_note(parsed.meta, args["status_parameter"])
        if note:
            result["setup"] = note
        if totals["truncated"]:
            result["limits"]["truncated"] = True
            result["limits"]["partial"] = True
        return _summary_first(result, totals)

    def status_set(
        self,
        tag: Any = None,
        family_name: Any = None,
        ids: Any = None,
        changes: Any = None,
        status: Any = None,
        from_status: Any = None,
        status_parameter: Any = None,
        status_labels: Any = None,
        max_changes: Any = None,
        on_error: Any = None,
        dry_run: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_status_set"
        try:
            labels = _labels(status_labels)
            sel = _selection(tag, family_name, ids)
            max_n = _int(max_changes, "max_changes", 1, 500, 200)
            explicit = bool(sel["ids"]) or changes not in (None, [])
            scope = bool(sel["tag"] or sel["family_name"])
            if explicit and scope:
                raise ValueError("give either ids / changes (explicit sparingen) or tag / family_name (every match), not both")
            if not explicit and not scope:
                raise ValueError("say which sparingen: ids with status, changes (id and status per sparing), or tag / family_name with status")
            pairs: List[List[Any]] = []
            target = ""
            if changes not in (None, []):
                if sel["ids"] or status not in (None, ""):
                    raise ValueError("changes carries its own status per id; leave ids and status out")
                if not isinstance(changes, list) or len(changes) > max_n:
                    raise ValueError(f"changes must be a list of at most {max_n} objects with id and status")
                seen: List[int] = []
                for c in changes:
                    if not isinstance(c, dict) or set(c) - {"id", "status"}:
                        raise ValueError("each change is an object with id and status only")
                    cid = _int(c.get("id"), "changes.id", 1, 2**62, 0)
                    if cid == 0 or cid in seen:
                        raise ValueError(f"changes.id {c.get('id')!r} is missing or listed twice")
                    seen.append(cid)
                    pairs.append([cid, _status_key(c.get("status"), labels, "changes.status")])
            else:
                if status in (None, ""):
                    raise ValueError("status is required: one of " + ", ".join(STATUS_KEYS))
                target = _status_key(status, labels, "status")
                if sel["ids"]:
                    if len(sel["ids"]) > max_n:
                        raise ValueError(f"{len(sel['ids'])} ids is more than max_changes={max_n}")
                    pairs = [[i, target] for i in sel["ids"]]
            froms = _status_words(from_status, labels, "from_status")
            if froms and not scope:
                raise ValueError("from_status only filters the tag / family_name form")
            args: Dict[str, Any] = {
                "status_parameter": _status_parameter(status_parameter),
                "labels": labels,
                "transitions": {k: list(v) for k, v in TRANSITIONS.items()},
                "from_unset": list(FROM_UNSET),
                "changes": pairs,
                "tag": sel["tag"],
                "family_name": sel["family_name"],
                "status": target,
                "from_status": froms,
                "max_changes": max_n,
                "on_error": _choice(on_error, ("abort", "skip"), "on_error", "abort"),
                "dry_run": _bool(dry_run, "dry_run", False),
            }
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "status_set.ipy", args, write=True, tool_executor=None, approved_executor=approved_executor)
        if early is not None or parsed is None:
            return early or {}
        extra = {"status_parameter": args["status_parameter"], "status_labels": labels, "transitions": TRANSITIONS}
        item_rows = [r for r in parsed.rows if r.get("row_type") == "item"]
        totals = {"requested": len(pairs) if pairs else None, "set": len([r for r in item_rows if r.get("action") == "set"]),
                  "unchanged": len([r for r in item_rows if r.get("action") == "unchanged"])}
        return _finish_write(tool, parsed, elapsed, workspace, extra=extra, dry_run_asked=args["dry_run"], totals=totals)

    def status_setup(
        self,
        status_parameter: Any = None,
        group_name: Any = None,
        categories: Any = None,
        shared_parameter_file: Any = None,
        on_error: Any = None,
        dry_run: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_status_setup"
        try:
            cats = _setup_categories(categories)
            path = ""
            if shared_parameter_file not in (None, ""):
                path = str(shared_parameter_file)
                if len(path) > 260 or any(ord(c) < 32 for c in path) or any(c in path for c in '<>"|*?') or not path.lower().endswith(".txt"):
                    raise ValueError("shared_parameter_file must be a path (at most 260 characters) to a shared parameter .txt file")
            args: Dict[str, Any] = {
                "status_parameter": _status_parameter(status_parameter),
                "group_name": _name(group_name if group_name not in (None, "") else DEFAULT_GROUP, "group_name"),
                "categories": [SETUP_CATEGORIES[c] for c in cats],
                "shared_parameter_file": path,
                "on_error": _choice(on_error, ("abort", "skip"), "on_error", "abort"),
                "dry_run": _bool(dry_run, "dry_run", False),
            }
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "status_setup.ipy", args, write=True, tool_executor=None, approved_executor=approved_executor)
        if early is not None or parsed is None:
            return early or {}
        totals = {"status_parameter": args["status_parameter"], "group_name": args["group_name"], "categories": cats}
        return _finish_write(tool, parsed, elapsed, workspace, dry_run_asked=args["dry_run"], totals=totals)

    # ---- copy to discipline models ------------------------------------------ #
    def export_spec(
        self,
        tag: Any = None,
        family_name: Any = None,
        ids: Any = None,
        link_ids: Any = None,
        link_name: Any = None,
        force_link_id: Any = None,
        size_parameters: Any = None,
        status_parameter: Any = None,
        status_labels: Any = None,
        discipline_parameter: Any = None,
        max_items: Any = None,
        save_as: Any = None,
        include_spec: Any = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_export_spec"
        try:
            labels = _labels(status_labels)
            args: Dict[str, Any] = _selection(tag, family_name, ids)
            lids: List[int] = []
            if link_ids not in (None, []):
                if not isinstance(link_ids, list) or len(link_ids) > 50:
                    raise ValueError("link_ids must be a list of at most 50 link instance ids")
                lids = [_int(i, "link_ids", 1, 2**62, 1) for i in link_ids]
            sizes: Dict[str, str] = {}
            if size_parameters not in (None, {}):
                sizes = self._size_parameters(size_parameters)
            name = _safe_save_name(save_as)
            args.update({
                "link_ids": lids,
                "link_name": _text(link_name, "link_name").strip() if link_name not in (None, "") else "",
                "force_link_id": None if force_link_id is None else _int(force_link_id, "force_link_id", 1, 2**62, 1),
                "size_parameters": sizes,
                "status_parameter": _status_parameter(status_parameter),
                "labels": labels,
                "discipline_parameter": _opt_name(discipline_parameter, "discipline_parameter"),
                "max_elements": _int(max_items, "max_items", 1, 500, 200),
            })
            inline = _bool(include_spec, "include_spec", name == "")
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "export_spec.ipy", args, write=False, tool_executor=tool_executor, approved_executor=None)
        if early is not None or parsed is None:
            return early or {}
        spec, unassigned = build_spec(parsed, labels, sizes)
        exported = sum(len(x["items"]) for x in spec["links"])
        reasons: Dict[str, int] = {}
        for u in unassigned:
            reasons[u.get("reason", "")] = reasons.get(u.get("reason", ""), 0) + 1
        bbox_sized = sum(1 for x in spec["links"] for i in x["items"] if i["size_mm"]["from"] == "bounding box")
        infos = list(parsed.infos)
        if bbox_sized:
            infos.append("SIZE_FROM_BOUNDING_BOX: %d item(s) have no size parameters read (pass size_parameters); their sizes are bounding box extents" % bbox_sized)
        if reasons.get("host_in_this_model"):
            infos.append("HOST_IN_THIS_MODEL: %d sparingen sit in hosts of this model, not of a link; they are not part of any link's spec" % reasons["host_in_this_model"])
        synthetic = ScriptOutput(
            summary=parsed.summary, fails=list(parsed.fails), infos=infos, rows=unassigned, meta=dict(parsed.meta),
            counts={"fail": parsed.counts.get("fail", len(parsed.fails)), "info": len(infos), "row": len(unassigned)},
        )
        result = assemble_result(tool, synthetic, PageSpec(limit=MAX_LIMIT), row_types={"source_id": "int", "link_id": "int"}, elapsed_ms=elapsed, workspace=workspace)
        totals: Dict[str, Any] = {
            "selected": int(parsed.meta.get("selected", "0") or 0), "exported": exported, "unassigned": len(unassigned),
            "unassigned_by_reason": reasons, "links": len(spec["links"]), "truncated": parsed.meta.get("truncated") == "1",
            "coordinates": "internal",
        }
        result["rows_are"] = "sparingen that go to no link, with the reason"
        result["active_document"] = ACTIVE_DOCUMENT_NOTE
        if name:
            path, err = save_json(workspace, name, spec)
            result["spec_file"] = {"name": name, "path": path}
            if err:
                result["spec_file"]["error"] = err
                inline = True
        if inline:
            result["spec"] = spec
        if totals["truncated"]:
            result["limits"]["truncated"] = True
            result["limits"]["partial"] = True
        return _summary_first(result, totals)

    def place_spec(
        self,
        spec: Any = None,
        spec_file: Any = None,
        link_instance_id: Any = None,
        tag: Any = None,
        mode: Any = None,
        family_name: Any = None,
        type_name: Any = None,
        size_parameters: Any = None,
        status_parameter: Any = None,
        status_labels: Any = None,
        copy_status: Any = None,
        skip_document_check: Any = None,
        sparing_family: Any = None,
        existing_tolerance_mm: Any = None,
        max_sparings: Any = None,
        on_error: Any = None,
        dry_run: Any = None,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_sparing_place_spec"
        try:
            if (spec in (None, {})) == (spec_file in (None, "")):
                raise ValueError("give exactly one of spec (the object from revit_sparing_export_spec) or spec_file (the name it saved under)")
            data = spec
            if spec_file not in (None, ""):
                if not is_safe_name(str(spec_file)):
                    raise ValueError("spec_file must be a plain name (letters, digits, - and _), as given to save_as")
                data, err = load_json(workspace, str(spec_file))
                if err:
                    raise ValueError(f"spec_file {spec_file!r}: {err}")
            link = _spec_link(data, link_instance_id)
            spec_labels = data.get("status_labels") if isinstance(data.get("status_labels"), dict) else None
            labels = _labels(status_labels if status_labels not in (None, {}) else spec_labels)
            copy = _bool(copy_status, "copy_status", True)
            raw_items = link.get("items")
            if not isinstance(raw_items, list) or not raw_items:
                raise ValueError("the chosen link has no items in the spec")
            if len(raw_items) > 500:
                raise ValueError("the chosen link has more than 500 items; export fewer (max_items) or split the spec")
            items = [_spec_item(i, r, labels, copy) for i, r in enumerate(raw_items)]
            keys = [i["key"] for i in items]
            if len(set(keys)) != len(keys):
                raise ValueError("the spec lists the same key twice")
            kinds = sorted({i["kind"] or "family" for i in items})
            m = _choice(mode, ("family", "opening"), "mode", kinds[0] if len(kinds) == 1 else None)
            args: Dict[str, Any] = {"tag": _tag(tag), "mode": m, "items": items}
            if m == "family":
                fams = sorted({(i["family_name"], i["type_name"]) for i in items if i["family_name"] and i["type_name"]})
                fam = _opt_name(family_name, "family_name") or (fams[0][0] if len(fams) == 1 else "")
                typ = _opt_name(type_name, "type_name") or (fams[0][1] if len(fams) == 1 else "")
                if not fam or not typ:
                    raise ValueError("family_name and type_name are required for mode 'family' (the spec holds no single family and type)")
                sizes_in = size_parameters if size_parameters not in (None, {}) else data.get("size_parameters")
                args["family_name"], args["type_name"], args["size_parameters"] = fam, typ, self._size_parameters(sizes_in)
            else:
                if family_name not in (None, "") or type_name not in (None, "") or size_parameters not in (None, {}):
                    raise ValueError("family_name, type_name and size_parameters belong to mode 'family'; leave them out for mode 'opening'")
                args["family_name"], args["type_name"], args["size_parameters"] = "", "", {}
            args["status_parameter"] = _opt_name(status_parameter, "status_parameter")
            args["status_value"] = labels["proposed"] if args["status_parameter"] else ""
            args["labels"] = labels
            args["expect"] = {"title": str(link.get("document_title") or ""), "guid": str(link.get("document_guid") or "")}
            args["skip_document_check"] = _bool(skip_document_check, "skip_document_check", False)
            args["sparing_family"] = _opt_name(sparing_family, "sparing_family") or args["family_name"]
            args["existing_tolerance_mm"] = _num(existing_tolerance_mm, "existing_tolerance_mm", 0.0, 1000.0, 50.0)
            args["max_sparings"] = _int(max_sparings, "max_sparings", 1, 500, 100)
            args["on_error"] = _choice(on_error, ("abort", "skip"), "on_error", "abort")
            args["dry_run"] = _bool(dry_run, "dry_run", False)
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)
        parsed, elapsed, early = _run(tool, "place_spec.ipy", args, write=True, tool_executor=None, approved_executor=approved_executor)
        if early is not None or parsed is None:
            return early or {}
        extra = {
            "spec_link": {"link_instance_id": link.get("link_instance_id"), "link_name": link.get("link_name"),
                          "document_title": args["expect"]["title"]},
            "active_document": ACTIVE_DOCUMENT_NOTE,
        }
        totals = {"spec_items": len(items), "mode": args["mode"],
                  "placed": len([r for r in parsed.rows if r.get("row_type") == "item" and r.get("kind") == "sparing"]),
                  "skipped": len([r for r in parsed.rows if r.get("row_type") == "item" and r.get("kind") == "skipped"])}
        return _finish_write(tool, parsed, elapsed, workspace, extra=extra, dry_run_asked=args["dry_run"], totals=totals)
