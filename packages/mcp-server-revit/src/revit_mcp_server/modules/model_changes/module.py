"""
model_changes module — "What changed since yesterday".

Commands:
  list_snapshots     — List saved snapshots with timestamps, newest first.
  compare_snapshots  — Plain-language delta between two saved snapshots:
                       elements added / removed / modified (by UniqueId),
                       parameter value changes (old -> new), counts per category.

Read-only. Snapshots are read from ``<workspace>/snapshots/{snapshot_id}.json``.
Outside mock mode, missing snapshots raise a clear error; no data is invented.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITEMS = 200


def _snap_dir(workspace: Any) -> Path:
    return workspace.allowed_directories[0] / "snapshots"


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _scan(workspace: Any) -> List[Dict[str, Any]]:
    """Snapshot headers, newest first. Unreadable files are skipped."""
    rows: List[Dict[str, Any]] = []
    folder = _snap_dir(workspace)
    if not folder.is_dir():
        return rows
    for path in folder.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            logger.warning("Skipping unreadable snapshot file %s", path)
            continue
        if not isinstance(data, dict):
            continue
        taken = _parse_time(data.get("taken_at"))
        if taken is None:
            taken = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        source = data.get("source") or {}
        rows.append({
            "snapshot_id": path.stem,
            "taken_at": taken.isoformat(),
            "model": source.get("doc_title") or source.get("doc_guid") or "",
            "element_count": len(data.get("elements") or []),
            "_taken": taken,
        })
    rows.sort(key=lambda r: (r["_taken"], r["snapshot_id"]), reverse=True)
    return rows


def _resolve(ref: str, workspace: Any) -> str:
    if ref in ("latest", "previous"):
        rows = _scan(workspace)
        idx = 0 if ref == "latest" else 1
        if len(rows) <= idx:
            raise ValueError(
                f"Cannot use '{ref}': only {len(rows)} saved snapshot(s) found. "
                "Capture snapshots first (one per day works well) and try again."
            )
        return rows[idx]["snapshot_id"]
    return ref


def _load(snapshot_id: str, workspace: Any) -> Dict[str, Any]:
    if "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:
        raise ValueError(f"Invalid snapshot id '{snapshot_id}'.")
    path = _snap_dir(workspace) / f"{snapshot_id}.json"
    if not path.exists():
        raise ValueError(
            f"Snapshot '{snapshot_id}' not found. Use list_snapshots to see the saved snapshots."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _label(el: Dict[str, Any]) -> str:
    parts = [el.get("category") or "Element", el.get("family"), el.get("type_name")]
    return " - ".join(p for p in parts if p)


def _pval(el: Dict[str, Any], name: str) -> Any:
    p = (el.get("params") or {}).get(name)
    return p.get("v") if isinstance(p, dict) else None


_LOC_TOL = 1e-6

LOCATION_MISSING_REASON = (
    "These snapshots do not record where elements are, so moved or rotated elements "
    "could not be detected. The Revit add-in needs to save each element's `location` "
    "(`xyz` and `rotation`) in the snapshot."
)


def _num_list(value: Any) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)):
        return None
    try:
        return [float(v) for v in value]
    except (TypeError, ValueError):
        return None


def _loc(el: Dict[str, Any]) -> Any:
    """Normalised location (xyz + rotation), or None when the element has none."""
    loc = el.get("location")
    if loc is None:
        return None
    if isinstance(loc, dict):
        xyz = _num_list(loc.get("xyz"))
        rot = loc.get("rotation")
        try:
            rot = float(rot) if rot is not None else None
        except (TypeError, ValueError):
            rot = None
        if xyz is None and rot is None:
            return None
        return {"xyz": xyz, "rotation": rot}
    xyz = _num_list(loc)
    return {"xyz": xyz, "rotation": None} if xyz is not None else None


def _loc_differs(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    ax, bx = a["xyz"], b["xyz"]
    if (ax is None) != (bx is None):
        return True
    if ax is not None and (len(ax) != len(bx) or any(abs(x - y) > _LOC_TOL for x, y in zip(ax, bx))):
        return True
    ar, br = a["rotation"], b["rotation"]
    if (ar is None) != (br is None):
        return True
    return ar is not None and abs(ar - br) > _LOC_TOL


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def compare_snapshot_data(snap_a: Dict[str, Any], snap_b: Dict[str, Any], max_items: int = DEFAULT_MAX_ITEMS) -> Dict[str, Any]:
    """Pure comparison of two snapshot dicts (older, newer)."""
    els_a = {e["uid"]: e for e in snap_a.get("elements", []) if isinstance(e, dict) and "uid" in e}
    els_b = {e["uid"]: e for e in snap_b.get("elements", []) if isinstance(e, dict) and "uid" in e}

    added = [els_b[u] for u in els_b if u not in els_a]
    removed = [els_a[u] for u in els_a if u not in els_b]

    modified: List[Dict[str, Any]] = []
    param_changes: List[Dict[str, Any]] = []
    unchanged = 0
    location_compared = 0
    for uid, new in els_b.items():
        old = els_a.get(uid)
        if old is None:
            continue
        changes: List[Dict[str, Any]] = []
        names = sorted(set(old.get("params") or {}) | set(new.get("params") or {}))
        for name in names:
            ov, nv = _pval(old, name), _pval(new, name)
            if ov != nv:
                changes.append({"parameter": name, "old": ov, "new": nv})
        other: List[str] = []
        if old.get("type_uid") != new.get("type_uid") or old.get("type_name") != new.get("type_name"):
            other.append("type")
        if old.get("level_uid") != new.get("level_uid"):
            other.append("level")
        lo, ln = _loc(old), _loc(new)
        if lo is not None and ln is not None:
            location_compared += 1
            if _loc_differs(lo, ln):
                other.append("location")
        if not changes and not other:
            unchanged += 1
            continue
        modified.append({
            "uid": uid,
            "category": new.get("category"),
            "description": _label(new),
            "parameter_changes": changes,
            "other_changes": other,
        })
        for c in changes:
            param_changes.append({"uid": uid, "category": new.get("category"), "description": _label(new), **c})

    cats = sorted({e.get("category") or "Unknown" for e in list(els_a.values()) + list(els_b.values())})
    per_category: Dict[str, Dict[str, int]] = {
        c: {"before": 0, "after": 0, "added": 0, "removed": 0, "modified": 0} for c in cats
    }
    for e in els_a.values():
        per_category[e.get("category") or "Unknown"]["before"] += 1
    for e in els_b.values():
        per_category[e.get("category") or "Unknown"]["after"] += 1
    for e in added:
        per_category[e.get("category") or "Unknown"]["added"] += 1
    for e in removed:
        per_category[e.get("category") or "Unknown"]["removed"] += 1
    for m in modified:
        per_category[m["category"] or "Unknown"]["modified"] += 1

    def brief(e: Dict[str, Any]) -> Dict[str, Any]:
        return {"uid": e["uid"], "category": e.get("category"), "description": _label(e)}

    cap = max(0, int(max_items))
    totals = {
        "added": len(added), "removed": len(removed), "modified": len(modified),
        "unchanged": unchanged, "parameter_changes": len(param_changes),
    }
    not_enough_data: List[Dict[str, str]] = []
    if (els_a or els_b) and location_compared == 0:
        not_enough_data.append({"check": "location", "reason": LOCATION_MISSING_REASON})
    summary = _summary(totals, per_category, len(els_a), len(els_b))
    if not_enough_data:
        summary += (" Not enough data to tell whether anything moved or rotated: "
                    + LOCATION_MISSING_REASON)
    return {
        "totals": totals,
        "location_checked": location_compared > 0,
        "elements_compared_on_location": location_compared,
        "not_enough_data": not_enough_data,
        "counts_per_category": per_category,
        "added": [brief(e) for e in added[:cap]],
        "removed": [brief(e) for e in removed[:cap]],
        "modified": modified[:cap],
        "parameter_changes": param_changes[:cap],
        "truncated": any(n > cap for n in (len(added), len(removed), len(modified), len(param_changes))),
        "summary": summary,
    }


def _summary(totals: Dict[str, int], per_cat: Dict[str, Dict[str, int]], before: int, after: int) -> str:
    if not (totals["added"] or totals["removed"] or totals["modified"]):
        return (f"No changes found in parameters, type or level across {_plural(after, 'element')}.")
    bits = []
    if totals["added"]:
        bits.append(f"{_plural(totals['added'], 'element')} added")
    if totals["removed"]:
        bits.append(f"{_plural(totals['removed'], 'element')} removed")
    if totals["modified"]:
        bits.append(f"{_plural(totals['modified'], 'element')} modified "
                    f"({_plural(totals['parameter_changes'], 'parameter change')})")
    text = f"The model went from {before} to {after} elements: " + ", ".join(bits) + "."
    busiest = sorted(
        ((c, v["added"] + v["removed"] + v["modified"]) for c, v in per_cat.items()),
        key=lambda x: (-x[1], x[0]),
    )
    busiest = [f"{c} ({n})" for c, n in busiest if n][:3]
    if busiest:
        text += " Most affected categories: " + ", ".join(busiest) + "."
    return text


class ModelChangesModule:
    def list_snapshots(self, limit: int = 20, workspace: Any = None, **_) -> Dict[str, Any]:
        rows = _scan(workspace)
        shown = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows[: max(0, int(limit))]]
        if shown:
            shown[0]["alias"] = "latest"
        if len(shown) > 1:
            shown[1]["alias"] = "previous"
        return {
            "total_snapshots": len(rows),
            "snapshots": shown,
            "hint": "Pass 'previous' as older_snapshot_id and 'latest' as newer_snapshot_id to compare the two newest.",
        }

    def compare_snapshots(
        self,
        older_snapshot_id: str = "",
        newer_snapshot_id: str = "",
        max_items: int = DEFAULT_MAX_ITEMS,
        workspace: Any = None,
        **_,
    ) -> Dict[str, Any]:
        if not older_snapshot_id and not newer_snapshot_id:
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock

            require_snapshot_or_mock("", "model_changes_compare_snapshots")
            mock = json.loads(generate_mock_snapshot().model_dump_json(by_alias=True))
            result = compare_snapshot_data(mock, mock, max_items)
            result.update({
                "mock": True,
                "data_source": "MOCK DATA - generated sample, not your model.",
                "older_snapshot_id": mock["snapshot_id"],
                "newer_snapshot_id": mock["snapshot_id"],
            })
            result["summary"] = "[MOCK DATA] " + result["summary"]
            return result
        if not older_snapshot_id or not newer_snapshot_id:
            raise ValueError("Provide both older_snapshot_id and newer_snapshot_id (or 'previous' and 'latest').")

        older_id = _resolve(older_snapshot_id, workspace)
        newer_id = _resolve(newer_snapshot_id, workspace)
        snap_a = _load(older_id, workspace)
        snap_b = _load(newer_id, workspace)
        guid_a = (snap_a.get("source") or {}).get("doc_guid")
        guid_b = (snap_b.get("source") or {}).get("doc_guid")
        if guid_a and guid_b and guid_a != guid_b:
            raise ValueError(
                f"Snapshots '{older_id}' and '{newer_id}' come from different Revit models "
                f"({(snap_a.get('source') or {}).get('doc_title') or guid_a} and "
                f"{(snap_b.get('source') or {}).get('doc_title') or guid_b}), so comparing them "
                "would show almost every element as added or removed. Pick two snapshots of "
                "the same model; list_snapshots shows the model of each."
            )
        result = compare_snapshot_data(snap_a, snap_b, max_items)
        warnings: List[str] = []
        if not (guid_a and guid_b):
            warnings.append(
                "Could not confirm both snapshots are of the same Revit model (a snapshot has no "
                "document id). If they are from different models the delta below is meaningless."
            )
        result["warnings"] = warnings
        result.update({
            "mock": False,
            "data_source": "Saved snapshots",
            "older_snapshot_id": older_id,
            "newer_snapshot_id": newer_id,
            "older_taken_at": snap_a.get("taken_at"),
            "newer_taken_at": snap_b.get("taken_at"),
        })
        return result
