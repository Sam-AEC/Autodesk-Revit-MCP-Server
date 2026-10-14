"""
revit_ifc module - check an exported IFC against the live Revit model (read-only).

Command (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  check   read-only   revit_ifc_check: what did the IFC export drop?

The most cited complaint about IFC from Revit is that the export silently drops elements, property sets,
classification or materials. ``revit_export`` (revit_docs) writes the file; this tool reads it back and compares.

Two halves:
  * IFC half (pure Python, ifcopenshell, no Revit): storeys, entity counts by class, per element GlobalId / Tag,
    property sets, classification references (NL/SfB, Uniformat / Assembly Code), material association (the BIM basis
    ILS asks for an IfcMaterial on every object), storey assignment, duplicates at one placement, and the origin
    (IfcSite placement plus IfcMapConversion).
  * Revit half (one read-mode script, the same seam as the revit module's checks: ``revit_execute_python`` with
    ``mode: "read"``, validated by security/read_mode before it skips the approval gate): for a bounded selection
    (ids, categories, Comments tag, level; ``max_elements`` default 2000, ``time_budget_s`` default 15) the ElementId,
    UniqueId, category, level, Assembly Code, material names, IfcGUID / IfcExportAs, the requested parameter values,
    and the survey point.

Join: IFC Tag = ElementId (what the Revit exporter writes), else GlobalId = the export GUID derived from the UniqueId,
else GlobalId = the element's IfcGUID parameter. Per category: model count vs exported count, missing elements, missing
classification and materials, storey gaps and mismatches, missing or different ``expect_parameters``.

Verdict: PASS only when every selected element was read, the file was read, something was compared and nothing failed.
Truncated or partial Revit reads, an unreadable file, ``ifc_only`` without defects, or an empty selection give
UNVERIFIED; defects give FAIL. The result follows revit_mcp_server.check_contract (verified / partial flags, paged
problem rows, a detail file in the workspace when rows are cut).

UNVERIFIED (needs a live Revit; here only exercised against the Revit API stub in tests/test_revit_ifc.py):
  * the Revit script as a whole, in particular GetMaterialIds, BasePoint.GetSurveyPoint / SharedPosition,
    ActiveProjectLocation.GetProjectPosition, and the built-in parameters UNIFORMAT_CODE, IFC_GUID,
    IFC_EXPORT_ELEMENT_AS and IFC_EXPORT_ELEMENT;
  * that the Revit IFC exporter writes the ElementId to Tag and derives GlobalId from the UniqueId the way
    ``ifc_guid_from_unique_id`` assumes (episode GUID with its last 32 bits XORed with the element id);
  * which Revit point the exporter's IfcSite / IfcMapConversion corresponds to: the origin offset is reported, not judged.
The IFC half is tested against real ifcopenshell with small generated files.
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

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
REVIT_SCRIPTS = MODULE_DIR.parent / "revit" / "scripts"
REVIT_PRELUDE = REVIT_SCRIPTS / "_prelude.ipy"
REVIT_HELPERS = REVIT_SCRIPTS / "_helpers.ipy"
READ_SCRIPT = "read_model.ipy"
EXECUTE_TOOL = "revit_execute_python"
TOOL = "revit_ifc_check"
MISSING = "<missing>"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

DEFAULT_CATEGORIES = (
    "OST_Walls", "OST_Floors", "OST_Roofs", "OST_Doors", "OST_Windows", "OST_Columns", "OST_StructuralColumns",
    "OST_StructuralFraming", "OST_Ceilings", "OST_Stairs", "OST_StairsRailing", "OST_GenericModel",
    "OST_CurtainWallPanels", "OST_CurtainWallMullions", "OST_Furniture", "OST_PipeCurves", "OST_DuctCurves",
    "OST_MechanicalEquipment", "OST_PlumbingFixtures",
)
# IFC classes that are not objects of their own (openings, projections, virtual boundaries).
NOT_OBJECTS = ("IfcFeatureElement", "IfcVirtualElement")
CLASSIFICATION_PROPS = ("assembly code", "assemblycode", "nlsfb", "nl-sfb", "nl/sfb", "classification code", "classificationcode")
_TAG = re.compile(r"^[ -~]{1,80}$")
_TOL_M = 0.001  # duplicates: same class, type, rotation and position within 1 mm
ROW_TYPES = {"id": "int"}

_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "path_outside_workspace": "Use a path inside the allowed workspace directories (the folder revit_export wrote to); plans/ and proofs/ are refused.",
    "file_not_found": "Export first with revit_export (format ifc), then pass the same path.",
    "ifc_unreadable": "The file is not an IFC that ifcopenshell can open. Export it again with revit_export; nothing was compared (UNVERIFIED).",
    "empty_selection": "No Revit element matched the selection; check categories, tag and level.",
    "too_many_elements": "Narrow the selection or raise max_elements.",
    "script_exception": "The embedded script failed inside Revit. It is read-only, so the model was not changed.",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id.",
}


# --------------------------------------------------------------------------- #
# Small helpers
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


def build_script(args: Dict[str, Any]) -> str:
    """Revit prelude + helpers + ``ARGS`` literal + the read script (read mode: no transaction anywhere)."""
    parts = [
        REVIT_PRELUDE.read_text(encoding="utf-8"),
        REVIT_HELPERS.read_text(encoding="utf-8"),
        f"ARGS = {py2_literal(args)}",
        (SCRIPT_DIR / READ_SCRIPT).read_text(encoding="utf-8"),
    ]
    return "\n\n".join(parts) + "\n"


def run_read_script(script: str, tool_executor: ToolExecutor) -> Any:
    """The only seam to Revit: ``revit_execute_python`` in mode 'read' (validated, no approval, no transaction)."""
    return tool_executor(EXECUTE_TOOL, {"script": script, "mode": "read"})


def _server_in_mock_mode() -> bool:
    try:
        from revit_mcp_server.config import BridgeMode, config

        return config.mode == BridgeMode.mock
    except Exception:  # noqa: BLE001 - a config problem must not hide a real bridge
        return False


def _ifcopenshell() -> Any:
    """Import ifcopenshell on first use (it is slow to import)."""
    import ifcopenshell
    import ifcopenshell.guid
    import ifcopenshell.util.element
    import ifcopenshell.util.placement
    import ifcopenshell.util.unit

    return ifcopenshell


def ifc_guid_from_unique_id(uid: str) -> Optional[str]:
    """The IFC GlobalId the Revit exporter derives from a UniqueId (UNVERIFIED against live Revit).

    UniqueId = ``<episode GUID>-<element id as 8 hex>``; the export GUID is the episode GUID with its last 32 bits
    XORed with the element id, compressed to the 22-character IFC form.
    """
    text = str(uid or "").strip()
    if len(text) != 45 or text[36] != "-":
        return None
    try:
        episode, element = text[:36], int(text[37:], 16)
        tail = int(episode[-8:], 16) ^ element
        hexed = (episode[:-8] + "%08x" % tail).replace("-", "")
        if len(hexed) != 32:
            return None
        return str(_ifcopenshell().guid.compress(hexed))
    except (ValueError, TypeError):
        return None


class _OutsideWorkspace(ValueError):
    pass


def _in_workspace(workspace: Any, candidate: Path) -> Path:
    """Same rule as revit_docs.export: resolve and require the path inside the sandbox (plans/ and proofs/ refused)."""
    if workspace is None or not getattr(workspace, "assert_in_workspace", None):
        raise _OutsideWorkspace("no workspace is configured, so no path can be validated")
    try:
        return workspace.assert_in_workspace(Path(candidate))
    except Exception as exc:  # noqa: BLE001 - WorkspaceViolation or an OS error while resolving
        raise _OutsideWorkspace(str(exc)) from exc


def _names(value: Any, what: str, most: int) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{what} must be a list of names")
    out: List[str] = []
    for v in value:
        text = str(v if v is not None else "").strip()
        if not text or len(text) > 120 or any(ord(c) < 32 for c in text):
            raise ValueError(f"{what}: each name must be 1-120 characters without control characters")
        if text not in out:
            out.append(text)
    if len(out) > most:
        raise ValueError(f"{what}: at most {most} names")
    return out


def _int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{what} must be an integer")
    return int(value)


def _bad_input(exc: Exception) -> Dict[str, Any]:
    return error_result(TOOL, "invalid_input", str(exc), hint=_HINTS["invalid_input"])


def _num_text(text: str) -> Optional[float]:
    try:
        v = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def compare_values(revit: str, ifc: Any) -> str:
    """'same', 'different' or 'not_compared' (a Revit value with units next to an IFC number in SI units)."""
    a = str(revit or "").strip()
    b = _value_text(ifc).strip()
    if a.lower() == b.lower():
        return "same"
    if a.lower() in ("yes", "no", "true", "false") and b.lower() in ("yes", "no", "true", "false"):
        return "same" if (a.lower() in ("yes", "true")) == (b.lower() in ("yes", "true")) else "different"
    na, nb = _num_text(a), _num_text(b)
    if na is not None and nb is not None:
        return "same" if abs(na - nb) <= 1e-6 * max(1.0, abs(na), abs(nb)) else "different"
    if (nb is not None or isinstance(ifc, (int, float))) and re.match(r"^-?\d", a):
        return "not_compared"
    return "different"


# --------------------------------------------------------------------------- #
# IFC half
# --------------------------------------------------------------------------- #
def _class_of(ref: Any) -> str:
    """'System:Code' of an IfcClassificationReference (IFC2x3 ItemReference / IFC4 Identification)."""
    code = getattr(ref, "Identification", None) if hasattr(ref, "Identification") else None
    if not code and hasattr(ref, "ItemReference"):
        code = getattr(ref, "ItemReference", None)
    code = code or getattr(ref, "Name", None) or "?"
    system = ""
    src = getattr(ref, "ReferencedSource", None)
    for _ in range(4):
        if src is None:
            break
        if src.is_a("IfcClassification"):
            system = getattr(src, "Name", "") or ""
            break
        src = getattr(src, "ReferencedSource", None)
    return f"{system}:{code}" if system else str(code)


def _type_of(el: Any) -> Any:
    try:
        return _ifcopenshell().util.element.get_type(el)
    except Exception:  # noqa: BLE001
        return None


def _storey_of(el: Any) -> Any:
    util = _ifcopenshell().util.element
    node = el
    for _ in range(12):
        try:
            container = util.get_container(node)
        except Exception:  # noqa: BLE001
            container = None
        if container is None:
            container = util.get_aggregate(node)
        if container is None:
            return None
        if container.is_a("IfcBuildingStorey"):
            return container
        node = container
    return None


def read_ifc(path: Path) -> Dict[str, Any]:
    """Parse the IFC once; return plain data. Raises on an unreadable file."""
    ios = _ifcopenshell()
    f = ios.open(str(path))
    try:
        scale = float(ios.util.unit.calculate_unit_scale(f))
    except Exception:  # noqa: BLE001
        scale = 1.0
    storeys = []
    for s in f.by_type("IfcBuildingStorey"):
        storeys.append({"name": s.Name or "", "elevation_m": round(float(s.Elevation) * scale, 4) if s.Elevation is not None else None, "guid": s.GlobalId})

    # classification and material per entity id (direct, then via the type)
    classes: Dict[int, List[str]] = {}
    for rel in f.by_type("IfcRelAssociatesClassification"):
        ref = rel.RelatingClassification
        label = _class_of(ref) if ref is not None and ref.is_a("IfcClassificationReference") else (getattr(ref, "Name", None) or "?")
        for obj in rel.RelatedObjects or []:
            classes.setdefault(obj.id(), []).append(label)
    with_material = set()
    for rel in f.by_type("IfcRelAssociatesMaterial"):
        for obj in rel.RelatedObjects or []:
            with_material.add(obj.id())
    pset_counts: Dict[str, int] = {}
    psets_of: Dict[int, List[str]] = {}
    for rel in f.by_type("IfcRelDefinesByProperties"):
        pdef = rel.RelatingPropertyDefinition
        name = getattr(pdef, "Name", None) or "?"
        for obj in rel.RelatedObjects or []:
            psets_of.setdefault(obj.id(), []).append(name)
            pset_counts[name] = pset_counts.get(name, 0) + 1

    products = [p for p in f.by_type("IfcElement") if not any(p.is_a(c) for c in NOT_OBJECTS)] + list(f.by_type("IfcSpace"))
    elements: List[Dict[str, Any]] = []
    by_class: Dict[str, int] = {}
    for p in products:
        cls = p.is_a()
        by_class[cls] = by_class.get(cls, 0) + 1
        t = _type_of(p)
        refs = list(classes.get(p.id(), []))
        if not refs and t is not None:
            refs = list(classes.get(t.id(), []))
        material = p.id() in with_material or (t is not None and t.id() in with_material)
        psets = list(psets_of.get(p.id(), []))
        if t is not None:
            psets += [getattr(ps, "Name", "?") for ps in (getattr(t, "HasPropertySets", None) or [])]
        storey = _storey_of(p)
        pos: Optional[Tuple[float, ...]] = None
        rot: Optional[Tuple[float, ...]] = None
        try:
            if p.ObjectPlacement is not None:
                m = ios.util.placement.get_local_placement(p.ObjectPlacement)
                pos = tuple(round(float(m[i][3]) * scale, 4) for i in range(3))
                rot = tuple(round(float(m[i][j]), 3) for i in range(3) for j in range(3))
        except Exception:  # noqa: BLE001
            pos = None
        tag = str(getattr(p, "Tag", None) or "").strip() if hasattr(p, "Tag") else ""
        elements.append({
            "ref": p,
            "guid": p.GlobalId,
            "class": cls,
            "name": p.Name or "",
            "object_type": getattr(p, "ObjectType", None) or (t.Name if t is not None else "") or "",
            "tag": tag,
            "classification": refs,
            "material": bool(material),
            "psets": psets,
            "storey": storey.Name if storey is not None else None,
            "pos": pos,
            "rot": rot,
        })
    return {
        "file": f,
        "schema": f.schema,
        "scale": scale,
        "storeys": storeys,
        "by_class": dict(sorted(by_class.items())),
        "pset_counts": dict(sorted(pset_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:40]),
        "elements": elements,
        "origin": _ifc_origin(f, scale),
    }


def _ifc_origin(f: Any, scale: float) -> Dict[str, Any]:
    out: Dict[str, Any] = {"site_m": None, "map_conversion_m": None, "ref_latitude": None, "ref_longitude": None, "ref_elevation_m": None}
    sites = f.by_type("IfcSite")
    if sites:
        site = sites[0]
        try:
            m = _ifcopenshell().util.placement.get_local_placement(site.ObjectPlacement)
            out["site_m"] = [round(float(m[i][3]) * scale, 4) for i in range(3)]
        except Exception:  # noqa: BLE001
            pass
        out["ref_latitude"] = list(site.RefLatitude) if getattr(site, "RefLatitude", None) else None
        out["ref_longitude"] = list(site.RefLongitude) if getattr(site, "RefLongitude", None) else None
        if getattr(site, "RefElevation", None) is not None:
            out["ref_elevation_m"] = round(float(site.RefElevation) * scale, 4)
    try:
        conversions = f.by_type("IfcMapConversion")
    except Exception:  # noqa: BLE001 - IFC2x3 has no IfcMapConversion
        conversions = []
    if conversions:
        mc = conversions[0]
        mscale = scale
        crs = getattr(mc, "TargetCRS", None)
        unit = getattr(crs, "MapUnit", None) if crs is not None else None
        if unit is not None:
            mscale = 0.001 if getattr(unit, "Prefix", None) == "MILLI" else 1.0
        out["map_conversion_m"] = [round(float(mc.Eastings or 0) * mscale, 4), round(float(mc.Northings or 0) * mscale, 4), round(float(mc.OrthogonalHeight or 0) * mscale, 4)]
    return out


def ifc_checks(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """IFC-only defects as problem rows: no storey, no material, no classification, duplicates."""
    rows: List[Dict[str, Any]] = []
    counts = {"no_storey": 0, "no_material": 0, "no_classification": 0, "duplicate_placement": 0, "no_psets": 0}
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for el in data["elements"]:
        base = {"id": None, "category": "", "ifc_guid": el["guid"], "ifc_class": el["class"]}
        if not el["psets"]:
            counts["no_psets"] += 1
        if el["class"] != "IfcSpace" and el["storey"] is None:
            counts["no_storey"] += 1
            rows.append({**base, "problem": "no_storey", "detail": "not contained in an IfcBuildingStorey"})
        if el["class"] != "IfcSpace" and not el["material"]:
            counts["no_material"] += 1
            rows.append({**base, "problem": "no_material", "detail": "no IfcRelAssociatesMaterial (direct or via the type)"})
        if not el["classification"]:
            counts["no_classification"] += 1
            rows.append({**base, "problem": "no_classification", "detail": "no IfcClassificationReference (direct or via the type)"})
        if el["pos"] is not None:
            key = (el["class"], el["object_type"], el["name"], el["rot"], tuple(round(v / _TOL_M) for v in el["pos"]))
            groups.setdefault(key, []).append(el)
    for group in groups.values():
        if len(group) < 2:
            continue
        for el in group[1:]:
            counts["duplicate_placement"] += 1
            rows.append({"id": None, "category": "", "ifc_guid": el["guid"], "ifc_class": el["class"], "problem": "duplicate_placement",
                         "detail": "same class, type and placement as %s" % group[0]["guid"]})
    return rows, counts


# --------------------------------------------------------------------------- #
# Revit half
# --------------------------------------------------------------------------- #
def _revit_read(args: Dict[str, Any], tool_executor: Optional[ToolExecutor]) -> Tuple[Optional[ScriptOutput], Optional[Dict[str, Any]], int]:
    """(parsed, error_result, elapsed_ms)."""
    if tool_executor is None:
        return None, error_result(TOOL, "no_bridge", "No connection to the Revit tools in this session.", hint="Run inside the AEC Model Bridge server, or pass ifc_only=true to check the file alone."), 0
    script = build_script(args)
    started = time.perf_counter()
    try:
        raw = run_read_script(script, tool_executor)
    except Exception as exc:  # noqa: BLE001 - classified into a structured error
        text = str(exc)
        kind = "timeout_running" if "timed out" in text.lower() or "timeout" in text.lower() else "bridge_error"
        return None, error_result(TOOL, kind, text, hint=_HINTS.get(kind, "Check that Revit is running with the add-in (revit_health), or pass ifc_only=true.")), 0
    elapsed = int((time.perf_counter() - started) * 1000)
    if isinstance(raw, dict) and (raw.get("mock") or (isinstance(raw.get("data"), dict) and raw["data"].get("mock"))):
        return None, mock_result(TOOL), elapsed
    if isinstance(raw, dict) and raw.get("status") == "running" and raw.get("request_id"):
        res = error_result(TOOL, "timeout_running", "Revit is still working on the read; nothing was compared.", hint=_HINTS["timeout_running"])
        res["request_id"] = raw.get("request_id")
        return None, res, elapsed
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict) and "output" not in raw:
        raw = raw["data"]
    if not isinstance(raw, dict) or raw.get("success") is False or "output" not in raw:
        msg = str(raw.get("error") if isinstance(raw, dict) else type(raw).__name__) or "no output"
        return None, error_result(TOOL, "script_error", msg, hint="Read-only: the model is unchanged."), elapsed
    parsed = parse_script_output(str(raw.get("output") or ""))
    if parsed.errors:
        kind, message = parsed.errors[0]
        return None, error_result(TOOL, kind, message, hint=_HINTS.get(kind, "")), elapsed
    if not parsed.summary and not parsed.counts:
        return None, error_result(TOOL, "unparsable_output", "The script printed no summary (ignored %d lines)." % parsed.ignored_lines), elapsed
    return parsed, None, elapsed


def _xyz(text: Optional[str]) -> Optional[List[float]]:
    try:
        vals = [float(v) for v in str(text).split(",")]
        return vals if len(vals) == 3 else None
    except (TypeError, ValueError):
        return None


def _join(data: Dict[str, Any], parsed: ScriptOutput, params: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, int]], Dict[str, Any]]:
    by_tag: Dict[str, Dict[str, Any]] = {}
    by_guid: Dict[str, Dict[str, Any]] = {}
    for el in data["elements"]:
        by_guid[el["guid"]] = el
        if el["tag"].lstrip("-").isdigit():
            by_tag.setdefault(el["tag"], el)
    ios = _ifcopenshell()
    rows: List[Dict[str, Any]] = []
    per_cat: Dict[str, Dict[str, int]] = {}
    matched_guids = set()
    stats = {"matched_by_tag": 0, "matched_by_guid": 0, "matched_by_ifc_guid": 0, "excluded": 0, "params_not_compared": 0}
    for r in parsed.rows:
        cat = r.get("category") or "?"
        c = per_cat.setdefault(cat, {"model": 0, "excluded": 0, "exported": 0, "missing": 0, "no_classification": 0, "no_material": 0,
                                     "no_storey": 0, "storey_mismatch": 0, "param_missing": 0, "param_mismatch": 0})
        rid = r.get("id", "")
        uid = r.get("uid", "")
        export_as = (r.get("export_as") or "").strip()
        export_flag = (r.get("export_flag") or "").strip().lower()
        if export_as.lower() == "dontexport" or export_flag in ("no", "nee", "0"):
            c["excluded"] += 1
            stats["excluded"] += 1
            continue
        c["model"] += 1
        el = by_tag.get(rid)
        how = "tag"
        if el is None:
            el, how = by_guid.get(ifc_guid_from_unique_id(uid) or ""), "guid"
        if el is None and r.get("ifc_guid"):
            el, how = by_guid.get(r["ifc_guid"].strip()), "ifc_guid"
        base = {"id": int(rid) if rid.lstrip("-").isdigit() else None, "category": cat}
        if el is None:
            c["missing"] += 1
            rows.append({**base, "ifc_guid": "", "ifc_class": "", "problem": "not_exported", "detail": "no IFC object with Tag %s or the GlobalId of UniqueId %s" % (rid, uid)})
            continue
        stats["matched_by_" + how] += 1
        matched_guids.add(el["guid"])
        c["exported"] += 1
        base.update(ifc_guid=el["guid"], ifc_class=el["class"])
        assembly = (r.get("assembly") or "").strip()
        if not el["classification"]:
            c["no_classification"] += 1
            detail = "no classification reference in the IFC" + (f"; Revit Assembly Code {assembly} was dropped" if assembly else "; Revit has no Assembly Code either")
            rows.append({**base, "problem": "no_classification", "detail": detail})
        materials = r.get("materials") or ""
        if not el["material"] and el["class"] != "IfcSpace":
            c["no_material"] += 1
            detail = "no IfcMaterial" + (f"; Revit materials {materials.replace('|', ', ')} were dropped" if materials else "; Revit reports no material either")
            rows.append({**base, "problem": "no_material", "detail": detail})
        level = r.get("level") or ""
        if el["storey"] is None and el["class"] != "IfcSpace":
            c["no_storey"] += 1
            rows.append({**base, "problem": "no_storey", "detail": f"not in an IfcBuildingStorey (Revit level {level or '?'})"})
        elif level and el["storey"] is not None and el["storey"] != level:
            c["storey_mismatch"] += 1
            rows.append({**base, "problem": "storey_mismatch", "detail": f"IFC storey {el['storey']}, Revit level {level}"})
        if params:
            try:
                psets = ios.util.element.get_psets(el["ref"])
            except Exception:  # noqa: BLE001
                psets = {}
            flat: Dict[str, Any] = {}
            for props in psets.values():
                for k, v in props.items():
                    if k != "id":
                        flat.setdefault(k.lower(), v)
            for i, name in enumerate(params):
                rv = r.get(f"p{i}", MISSING)
                if rv == MISSING:
                    continue  # the model element has no such parameter: nothing to export
                if name.lower() not in flat:
                    c["param_missing"] += 1
                    rows.append({**base, "problem": "param_missing", "detail": f"{name} = {rv!r} in Revit, not in any IFC property set"})
                    continue
                verdict = compare_values(rv, flat[name.lower()])
                if verdict == "different":
                    c["param_mismatch"] += 1
                    rows.append({**base, "problem": "param_mismatch", "detail": f"{name}: Revit {rv!r}, IFC {_value_text(flat[name.lower()])!r}"})
                elif verdict == "not_compared":
                    stats["params_not_compared"] += 1
    extra: Dict[str, int] = {}
    for el in data["elements"]:
        if el["guid"] not in matched_guids:
            extra[el["class"]] = extra.get(el["class"], 0) + 1
    stats["ifc_not_in_selection"] = sum(extra.values())
    stats["ifc_not_in_selection_by_class"] = dict(sorted(extra.items()))  # type: ignore[assignment]
    return rows, per_cat, stats


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
FAIL_TEXT = {
    "not_exported": ("NOT_EXPORTED", "model element(s) are not in the IFC"),
    "no_classification": ("NO_CLASSIFICATION", "exported element(s) have no classification reference"),
    "no_material": ("NO_MATERIAL", "exported element(s) have no IfcMaterial"),
    "no_storey": ("NO_STOREY", "exported element(s) are not assigned to a storey"),
    "storey_mismatch": ("STOREY_MISMATCH", "exported element(s) sit on another storey than their Revit level"),
    "param_missing": ("PARAM_MISSING", "expected parameter value(s) did not reach the IFC"),
    "param_mismatch": ("PARAM_MISMATCH", "expected parameter value(s) differ in the IFC"),
    "duplicate_placement": ("DUPLICATE_PLACEMENT", "IFC object(s) repeat another of the same class and type at the same placement"),
}


def _fail_lines(rows: List[Dict[str, Any]]) -> List[str]:
    """One FAIL line per (problem, category) with the first ids, so a big model gives a few lines."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["problem"], r.get("category") or r.get("ifc_class") or "?"), []).append(r)
    lines = []
    for (problem, cat), items in sorted(groups.items()):
        code, text = FAIL_TEXT[problem]
        ids = [str(r["id"]) if r.get("id") is not None else r.get("ifc_guid", "") for r in items[:10]]
        more = "" if len(items) <= 10 else f" (+{len(items) - 10} more)"
        lines.append(f"{code}: {cat}: {len(items)} {text}: {', '.join(ids)}{more}")
    return lines


def _origin_report(ifc_origin: Dict[str, Any], meta: Optional[Dict[str, str]]) -> Dict[str, Any]:
    ifc_point = [0.0, 0.0, 0.0]
    for key in ("map_conversion_m", "site_m"):
        if ifc_origin.get(key):
            ifc_point = [a + b for a, b in zip(ifc_point, ifc_origin[key])]
    report: Dict[str, Any] = {"ifc": ifc_origin, "ifc_origin_shared_m": [round(v, 4) for v in ifc_point]}
    if meta is None:
        return report
    revit = {k: _xyz(meta.get(k)) for k in ("survey_internal_m", "survey_shared_m", "base_point_internal_m", "base_point_shared_m", "origin_shared_m")}
    report["revit"] = revit
    survey = revit.get("survey_shared_m")
    if survey is not None:
        off = [round(a - b, 4) for a, b in zip(ifc_point, survey)]
        report["offset_to_survey_point_m"] = off
        report["offset_to_survey_point_distance_m"] = round(math.sqrt(sum(v * v for v in off)), 4)
    origin = revit.get("origin_shared_m")
    if origin is not None:
        off = [round(a - b, 4) for a, b in zip(ifc_point, origin)]
        report["offset_to_internal_origin_m"] = off
    return report


class RevitIfcModule:

    def check(
        self,
        path: Any = None,
        categories: Any = None,
        ids: Any = None,
        tag: Any = None,
        level: Any = None,
        expect_parameters: Any = None,
        max_elements: Any = 2000,
        time_budget_s: Any = 15,
        ifc_only: Any = False,
        limit: Any = 50,
        offset: Any = 0,
        count_only: Any = False,
        fields: Any = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        # ---- arguments (nothing leaves the server before they are valid) ---- #
        try:
            if not isinstance(path, str) or not path.strip():
                raise ValueError("path is required")
            target = Path(path)
            if target.suffix.lower() != ".ifc":
                raise ValueError("path must end in .ifc")
            target = _in_workspace(workspace, target)
            cats = _names(categories, "categories", 60)
            id_list = [] if ids is None else [_int(v, "ids") for v in (ids if isinstance(ids, (list, tuple)) else [ids])]
            if len(id_list) > 20000:
                raise ValueError("ids: at most 20000")
            tag_text = str(tag or "")
            if tag_text and not _TAG.match(tag_text):
                raise ValueError("tag must be 1-80 printable ASCII characters")
            level_text = str(level or "").strip()
            if len(level_text) > 200:
                raise ValueError("level is longer than 200 characters")
            params = _names(expect_parameters, "expect_parameters", 30)
            cap = _int(max_elements if max_elements is not None else 2000, "max_elements")
            if not 1 <= cap <= 20000:
                raise ValueError("max_elements must be between 1 and 20000")
            if isinstance(time_budget_s, bool) or not isinstance(time_budget_s if time_budget_s is not None else 15, (int, float)):
                raise ValueError("time_budget_s must be a number")
            budget = float(time_budget_s if time_budget_s is not None else 15)
            if not 1 <= budget <= 120:
                raise ValueError("time_budget_s must be between 1 and 120")
        except _OutsideWorkspace as exc:
            return error_result(TOOL, "path_outside_workspace", str(exc), hint=_HINTS["path_outside_workspace"])
        except (TypeError, ValueError) as exc:
            return _bad_input(exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        if not target.is_file():
            return {**error_result(TOOL, "file_not_found", f"{target} does not exist", hint=_HINTS["file_not_found"]), "verdict": "UNVERIFIED", "verified": False}

        # ---- IFC half ---- #
        started = time.perf_counter()
        try:
            data = read_ifc(target)
        except Exception as exc:  # noqa: BLE001 - any parser failure means nothing was compared
            return {**error_result(TOOL, "ifc_unreadable", f"{type(exc).__name__}: {exc}", hint=_HINTS["ifc_unreadable"]), "verdict": "UNVERIFIED", "verified": False}
        ifc_rows, ifc_counts = ifc_checks(data)
        ifc_summary = {
            "path": str(target),
            "schema": data["schema"],
            "storeys": data["storeys"],
            "objects": len(data["elements"]),
            "by_class": data["by_class"],
            "property_sets": data["pset_counts"],
            "objects_without_property_sets": ifc_counts["no_psets"],
            "objects_without_storey": ifc_counts["no_storey"],
            "objects_without_material": ifc_counts["no_material"],
            "objects_without_classification": ifc_counts["no_classification"],
            "duplicates_at_same_placement": ifc_counts["duplicate_placement"],
        }

        if bool(ifc_only):
            not_checked = [
                "model elements missing from the IFC (needs Revit)",
                "Revit Assembly Code and materials dropped by the export (needs Revit)",
                "expect_parameters values (needs Revit)" if params else "parameter values (needs Revit and expect_parameters)",
                "storey vs Revit level, origin vs survey point (needs Revit)",
            ]
            infos = [f"NOT_CHECKED: {t}" for t in not_checked]
            if not data["storeys"]:
                ifc_rows.append({"id": None, "category": "", "ifc_guid": "", "ifc_class": "IfcBuildingStorey", "problem": "no_storey", "detail": "the file has no IfcBuildingStorey"})
            fails = _fail_lines(ifc_rows)
            verdict = "FAIL" if fails else "UNVERIFIED"
            summary = f"{verdict}: IFC only ({data['schema']}, {len(data['elements'])} objects, {len(data['storeys'])} storeys); {len(ifc_rows)} problem(s) in the file; the model was not compared"
            return self._result(ifc_rows, fails, infos, page, workspace, summary, verdict, verified=False, partial=False,
                                elapsed=int((time.perf_counter() - started) * 1000),
                                extra={"ifc": ifc_summary, "origin": _origin_report(data["origin"], None), "not_checked": not_checked, "ifc_only": True})

        # ---- Revit half ---- #
        if _server_in_mock_mode():
            return {**mock_result(TOOL), "verdict": "UNVERIFIED", "ifc": ifc_summary}
        args = {
            "ids": id_list, "tag": tag_text, "categories": cats, "default_categories": list(DEFAULT_CATEGORIES), "level": level_text,
            "params": params, "max_elements": cap, "time_budget_s": budget,
        }
        parsed, err, elapsed = _revit_read(args, tool_executor)
        if err is not None or parsed is None:
            err = dict(err or {})
            err.update(verdict="UNVERIFIED", verified=False, ifc=ifc_summary)
            if err.get("ok") is not False:  # mock: keep its shape, but say what was not compared
                err.setdefault("info", []).append("UNVERIFIED: the model side did not run; only the IFC was read.")
            return err
        truncated = parsed.meta.get("truncated") == "1"
        partial = parsed.meta.get("partial") == "1" or truncated
        rows, per_cat, stats = _join(data, parsed, params)
        dup_rows = [r for r in ifc_rows if r["problem"] == "duplicate_placement"]
        rows += dup_rows
        fails = _fail_lines(rows)
        infos = list(parsed.infos)
        model_total = sum(c["model"] for c in per_cat.values())
        if truncated:
            infos.append(f"TRUNCATED: the Revit side stopped at {parsed.meta.get('read', '?')} element(s) (max_elements {cap} or time budget {budget:g}s); unread elements were not compared")
        if stats["excluded"]:
            infos.append(f"EXCLUDED: {stats['excluded']} element(s) are set not to export (IfcExportAs DontExport or Export to IFC = No) and were not counted")
        if stats["params_not_compared"]:
            infos.append(f"PARAM_NOT_COMPARED: {stats['params_not_compared']} value(s) carry units in Revit and a bare number in the IFC; compare them by hand")
        if stats["ifc_not_in_selection"]:
            infos.append(f"IFC_NOT_IN_SELECTION: {stats['ifc_not_in_selection']} IFC object(s) match no selected Revit element (other categories, or not from this model)")
        origin = _origin_report(data["origin"], parsed.meta)
        if "offset_to_survey_point_m" in origin:
            infos.append("ORIGIN: IFC origin (map conversion + site) minus Revit survey point (shared) = %s m; which Revit point the exporter uses is not judged" % origin["offset_to_survey_point_m"])
        else:
            infos.append("ORIGIN_NOT_COMPARED: the survey point could not be read from Revit")
        if fails:
            verdict = "FAIL"
        elif partial or model_total == 0:
            verdict = "UNVERIFIED"
        else:
            verdict = "PASS"
        if model_total == 0:
            infos.append("NOTHING_COMPARED: no exportable Revit element was selected")
        missing = sum(c["missing"] for c in per_cat.values())
        summary = f"{verdict}: {model_total - missing} of {model_total} model element(s) found in the IFC; {len(rows)} problem(s)"
        if partial:
            summary += "; Revit side TRUNCATED or PARTIAL"
        return self._result(rows, fails, infos, page, workspace, summary, verdict, verified=not partial and model_total > 0, partial=partial,
                            elapsed=elapsed + int((time.perf_counter() - started) * 1000), parsed=parsed,
                            extra={"ifc": ifc_summary, "per_category": dict(sorted(per_cat.items())), "join": stats, "origin": origin,
                                   "truncated": truncated, "ifc_only": False, "not_checked": []})

    @staticmethod
    def _result(rows: List[Dict[str, Any]], fails: List[str], infos: List[str], page: PageSpec, workspace: Any, summary: str, verdict: str,
                *, verified: bool, partial: bool, elapsed: int, extra: Dict[str, Any], parsed: Optional[ScriptOutput] = None) -> Dict[str, Any]:
        meta = dict(parsed.meta) if parsed is not None else {}
        meta["verified"] = "1" if verified else "0"
        meta["partial"] = "1" if partial else "0"
        synthetic = ScriptOutput(
            summary=summary,
            fails=fails,
            infos=infos,
            rows=[{k: "" if v is None else str(v) for k, v in r.items()} for r in rows],
            meta=meta,
            counts={"fail": len(fails), "info": len(infos), "row": len(rows)},
        )
        result = assemble_result(
            TOOL,
            synthetic,
            page,
            row_types=ROW_TYPES,
            sort_key=lambda r: (str(r.get("problem") or ""), str(r.get("category") or ""), r.get("id") or 0, str(r.get("ifc_guid") or "")),
            elapsed_ms=elapsed,
            workspace=workspace,
            summary=summary,
            extra={**extra, "verdict": verdict},
        )
        result["verified"] = verified
        result["limits"]["partial"] = partial
        return result
