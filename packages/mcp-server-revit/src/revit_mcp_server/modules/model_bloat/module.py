"""model_bloat module - read-only model clean-up (bloat) audit.

Command:
  audit - report purge candidates and other model weight, sorted by likely impact.

This module NEVER deletes, purges or changes anything. Removing items it
reports must go through an approved plan (plan_actions -> approve_plan).

What the snapshot carries (see semantic/models.py):
  - Instances: ElementRecord.family / type_name / type_uid. Instance counts are
    NOT stored as a number; they are derived here by counting the element
    records that point at each type. This is only exact when the snapshot
    contains every placed instance of the model.
  - Types: TypeRecord.family / type_name / family_source (system|loadable|inplace).
  - Imported CAD: there is no dedicated field. Detected from element records with
    class "ImportInstance" / "CADLinkType" or a .dwg/.dxf/.dgn name.
  Honesty rule: a check whose data is missing reports "not_enough_data" (with
  what is missing) and the cleanliness score is null ("not rated"), never 100.
  Today's live snapshots carry no `types` list and no CAD records, so they are
  not rated until the add-in extractor supplies them. CAD "none found" is only
  trusted if the snapshot has a top-level `cad_scanned: true` or contains CAD.
  Not carried by the snapshot (not reported): nested/shared family usage, types
  used only by other types, file size, and anything Revit stores outside elements.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_LARGE_TYPE_THRESHOLD = 25
DEFAULT_MAX_ITEMS = 50
CAD_CLASSES = {"ImportInstance", "CADLinkType"}
CAD_EXTENSIONS = (".dwg", ".dxf", ".dgn")

PURGE_NOTE = (
    "This report only reads the model. Nothing has been deleted or purged. "
    "Removing anything listed here must go through an approved plan "
    "(plan_actions, then approve_plan) after a human has reviewed it."
)
COUNT_CAVEAT = (
    "Usage is counted from the elements in the snapshot. If the snapshot was "
    "filtered or partial, or a type is used only inside another family or type, "
    "it can look unused when it is not. Check in Revit before purging."
)


def _load_snapshot(snapshot_id: str, workspace: Any) -> Dict[str, Any]:
    path = Path(workspace.allowed_directories[0]) / "snapshots" / f"{snapshot_id}.json"
    if not path.exists():
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_data(snapshot_id: str, workspace: Any) -> Tuple[List[dict], List[dict], bool]:
    if not snapshot_id:
        from revit_mcp_server.semantic.engine import generate_mock_snapshot

        snap = generate_mock_snapshot()
        return (
            [el.model_dump(by_alias=True) for el in snap.elements],
            [t.model_dump() for t in snap.types],
            False,
        )
    data = _load_snapshot(snapshot_id, workspace)
    return data.get("elements", []), data.get("types", []), data.get("cad_scanned") is True


def _param_value(el: dict, *names: str) -> Any:
    params = el.get("params") or {}
    for name in names:
        val = params.get(name)
        if isinstance(val, dict):
            val = val.get("v")
        if val is not None:
            return val
    return None


def _cad_kind(el: dict) -> Optional[str]:
    """Return 'linked', 'imported' or None for an element record."""
    cls = el.get("class") or el.get("cls") or ""
    name = el.get("type_name") or el.get("family") or ""
    if cls not in CAD_CLASSES and not str(name).lower().endswith(CAD_EXTENSIONS):
        return None
    linked = _param_value(el, "IsLinked", "Is Linked", "is_linked")
    if cls == "CADLinkType" or linked in (True, 1, "true", "True", "Yes", "yes"):
        return "linked"
    return "imported"


def _check(ok: bool, reason: str, *missing: List[str]) -> Dict[str, Any]:
    gaps = [m for group in missing for m in group]
    if ok:
        return {"status": "ran", "reason": None, "missing": []}
    return {"status": "not_enough_data", "reason": reason, "missing": gaps}


def _impact(weight: float) -> str:
    return "high" if weight >= 8 else "medium" if weight >= 3 else "low"


def _cap(items: List[dict], max_items: int) -> Dict[str, Any]:
    return {"total": len(items), "shown": min(len(items), max_items), "items": items[:max_items]}


def _sorted(items: List[dict], key: str) -> List[dict]:
    return sorted(items, key=lambda i: (-i["weight"], str(i.get(key))))


class ModelBloatModule:
    def audit(
        self,
        snapshot_id: str = "",
        workspace: Any = None,
        large_type_threshold: int = DEFAULT_LARGE_TYPE_THRESHOLD,
        max_items: int = DEFAULT_MAX_ITEMS,
        **_,
    ) -> Dict[str, Any]:
        threshold = int(large_type_threshold or DEFAULT_LARGE_TYPE_THRESHOLD)
        limit = max(1, int(max_items or DEFAULT_MAX_ITEMS))
        elements, types, cad_scanned = _get_data(snapshot_id, workspace)

        # Usage counting (derived; the snapshot has no instance-count field).
        by_uid: Dict[str, int] = defaultdict(int)
        by_name: Dict[Tuple[str, str], int] = defaultdict(int)
        placed_total = 0
        cad_items: List[dict] = []
        for el in elements:
            kind = _cad_kind(el)
            if kind:
                cad_items.append({
                    "name": el.get("type_name") or el.get("family") or "(unnamed CAD)",
                    "kind": kind,
                    "element_id": el.get("element_id"),
                })
                continue
            if el.get("type_uid"):
                by_uid[el["type_uid"]] += 1
                placed_total += 1
            elif el.get("family") and el.get("type_name"):
                by_name[(el["family"], el["type_name"])] += 1
                placed_total += 1

        types_available = bool(types)
        usage_available = placed_total > 0 and types_available
        # A CAD scan is trusted only if the snapshot says it looked for CAD
        # (cad_scanned) or actually found some. "No CAD records" alone could just
        # mean the extractor never collects them.
        cad_available = cad_scanned or bool(cad_items)

        def used(t: dict) -> int:
            return by_uid.get(t.get("uid"), 0) + by_name.get((t.get("family"), t.get("type_name")), 0)

        fam_types: Dict[str, List[dict]] = defaultdict(list)
        for t in types:
            if t.get("family"):
                fam_types[t["family"]].append(t)

        unused_families: List[dict] = []
        unused_types: List[dict] = []
        inplace: List[dict] = []
        large: List[dict] = []

        for fam, tlist in fam_types.items():
            is_inplace = any(t.get("family_source") == "inplace" for t in tlist)
            is_system = not is_inplace and tlist[0].get("family_source") == "system"
            counts = {t.get("type_name"): used(t) for t in tlist}
            fam_total = sum(counts.values())
            if is_inplace:
                w = 6 + min(fam_total, 20) * 0.25
                inplace.append({
                    "family": fam,
                    "placed_instances": fam_total if usage_available else None,
                    "weight": round(w, 1), "impact": _impact(w),
                    "advice": "In-place families are slow and cannot be reused; consider rebuilding as a loadable family.",
                })
            if len(tlist) > threshold:
                w = 2 + (len(tlist) - threshold) / 5
                large.append({
                    "family": fam, "type_count": len(tlist),
                    "weight": round(w, 1), "impact": _impact(w),
                    "advice": f"{len(tlist)} types is a lot; keep only the sizes this project uses.",
                })
            if not usage_available:
                continue
            if fam_total == 0 and not is_system:
                w = 2 + 0.5 * len(tlist) + (3 if is_inplace else 0)
                unused_families.append({
                    "family": fam, "type_count": len(tlist),
                    "weight": round(w, 1), "impact": _impact(w),
                    "advice": "No placed instances: the whole family is a purge candidate.",
                })
            else:
                for tn, n in counts.items():
                    if n == 0:
                        unused_types.append({
                            "family": fam, "type_name": tn, "weight": 0.5, "impact": "low",
                            "advice": "Type has no placed instances; the family itself is still in use.",
                        })

        unused_families = _sorted(unused_families, "family")
        unused_types = _sorted(unused_types, "family")
        inplace = _sorted(inplace, "family")
        large = _sorted(large, "family")
        for c in cad_items:
            imported = c["kind"] == "imported"
            c["weight"] = 10.0 if imported else 2.0
            c["impact"] = _impact(c["weight"])
            c["advice"] = (
                "Imported (embedded) CAD is a common cause of slow models; prefer a link, or remove it if no longer needed."
                if imported else "Linked CAD file; keep only if still referenced."
            )
        cad_items = _sorted(cad_items, "name")
        imported_cad = [c for c in cad_items if c["kind"] == "imported"]
        linked_cad = [c for c in cad_items if c["kind"] == "linked"]

        sections = [
            (sum(c["weight"] for c in imported_cad), f"{len(imported_cad)} imported CAD file(s) embedded in the model", len(imported_cad)),
            (sum(i["weight"] for i in inplace), f"{len(inplace)} in-place family(ies)", len(inplace)),
            (sum(i["weight"] for i in large), f"{len(large)} family(ies) with more than {threshold} types", len(large)),
            (sum(i["weight"] for i in unused_families), f"{len(unused_families)} unused family(ies) with no placed instances", len(unused_families)),
            (sum(c["weight"] for c in linked_cad), f"{len(linked_cad)} linked CAD file(s)", len(linked_cad)),
            (sum(i["weight"] for i in unused_types), f"{len(unused_types)} unused type(s) inside families that are otherwise in use", len(unused_types)),
        ]
        sections.sort(key=lambda s: -s[0])
        findings = [s[1] for s in sections if s[2] > 0]

        checks = {
            "unused_families_and_types": _check(
                usage_available,
                "Unused families and types cannot be worked out from this snapshot.",
                [] if types_available else ["a type list (the 'types' catalog of every loaded family type)"],
                [] if placed_total > 0 else ["placed-instance records that point at their type"],
            ),
            "in_place_families": _check(
                types_available,
                "In-place families are identified from the type list, which this snapshot does not carry.",
                ["a type list with family_source (system, loadable or inplace)"],
            ),
            "families_with_very_many_types": _check(
                types_available,
                "Type counts per family need the type list, which this snapshot does not carry.",
                ["a type list (the 'types' catalog of every loaded family type)"],
            ),
            "imported_cad": _check(
                cad_available,
                "This snapshot has no CAD records, and does not say whether CAD was looked for, "
                "so 'no CAD found' cannot be trusted.",
                ["records for imported/linked CAD (ImportInstance and CADLinkType elements) or cad_scanned: true"],
            ),
        }
        missing_checks = [k for k, c in checks.items() if c["status"] != "ran"]
        rated = not missing_checks
        if rated:
            score: Optional[int] = max(0, round(100 - sum(s[0] for s in sections)))
            label = "clean" if score >= 85 else "needs tidying" if score >= 60 else "heavy" if score >= 30 else "very heavy"
        else:
            score, label = None, "not rated"
        if not types_available:
            inplace, large, unused_families, unused_types = [], [], [], []
        if not cad_available:
            cad_items, imported_cad, linked_cad = [], [], []

        notes = [PURGE_NOTE]
        if usage_available:
            notes.append(COUNT_CAVEAT)
        elif types_available:
            notes.append(
                "This snapshot has no placed-instance records that point at types "
                "(no type_uid, or family and type_name, on any element), so unused "
                "families and types could not be worked out and are not listed."
            )
        for k in missing_checks:
            notes.append(f"Not enough data for '{k}': {checks[k]['reason']}")

        if rated:
            summary = f"Model cleanliness: {score}/100 ({label}). " + (
                "Biggest issues first: " + "; ".join(findings) + "." if findings else "Nothing to tidy was found."
            )
        else:
            why = " ".join(checks[k]["reason"] for k in missing_checks)
            summary = (
                "Model cleanliness: not rated: not enough data in this snapshot. "
                + why
                + (" What was checked found: " + "; ".join(findings) + "." if findings else "")
            )

        def sect(name: str, items: List[dict]) -> Dict[str, Any]:
            if checks[name]["status"] != "ran":
                return {"status": "not_enough_data", "reason": checks[name]["reason"],
                        "missing": checks[name]["missing"], "total": None, "shown": 0, "items": []}
            return _cap(items, limit)

        return {
            "read_only": True,
            "summary": summary,
            "checks": checks,
            "cleanliness": {
                "score": score,
                "label": label,
                "note": (
                    "A rough estimate from the counts below, not an exact measure of file size or speed."
                    if rated else "No score is given: at least one check could not run (see 'checks')."
                ),
            },
            "usage_counts_available": usage_available,
            "headline_findings": findings,
            "imported_cad": sect("imported_cad", cad_items),
            "in_place_families": sect("in_place_families", inplace),
            "families_with_very_many_types": sect("families_with_very_many_types", large),
            "unused_families": sect("unused_families_and_types", unused_families),
            "unused_types": sect("unused_families_and_types", unused_types),
            "notes": notes,
        }
