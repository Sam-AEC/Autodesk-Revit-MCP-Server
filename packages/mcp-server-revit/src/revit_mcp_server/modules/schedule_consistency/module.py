"""
schedule_consistency module - door and room schedule consistency check (F8).

Command:
  check_doors_and_rooms - read-only checks over a saved snapshot.

Nothing here changes the model. Suggested Marks are a proposal for a human to
review; applying them would need a separate, approved plan (not created here).

Checks (check_id):
  door_missing_mark, door_duplicate_mark, door_mark_pattern_mismatch,
  door_missing_room, door_same_room, door_in_unnumbered_room,
  room_missing_number, room_duplicate_number, room_zero_area

Door From/To room data is read from the instance parameters "From Room" and
"To Room" (room UniqueId or room number). If a snapshot carries neither, the
room-related door checks are reported as skipped instead of flagging every door.
UNVERIFIED against live Revit: that the extractor writes these parameters.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

FROM_KEYS = ("From Room", "FromRoom", "From Room Number")
TO_KEYS = ("To Room", "ToRoom", "To Room Number")


def _pv(el: Dict[str, Any], name: str) -> Any:
    p = (el.get("params") or {}).get(name)
    if isinstance(p, dict):
        return p.get("v")
    return p


PLACEMENT_UNKNOWN_REASON = (
    "Not enough data to say whether zero-area rooms are placed or unplaced: this snapshot "
    "has no room level or location. The Revit add-in needs to save each room's level and "
    "placement."
)
ROOM_DATA_MISSING_REASON = (
    "Not enough data: this snapshot has no From Room / To Room for doors, so this check "
    "could not be run (it is NOT a pass). The Revit add-in needs to save each door's "
    "FromRoom and ToRoom."
)


def _blank(v: Any) -> bool:
    if isinstance(v, (dict, list, tuple)):
        return len(v) == 0
    return v is None or (isinstance(v, str) and v.strip() == "")


def _txt(v: Any) -> str:
    return "" if _blank(v) else str(v).strip()


def _label(el: Dict[str, Any]) -> str:
    return str(el.get("type_name") or _pv(el, "Name") or el.get("category") or "")


def _room_ref(door: Dict[str, Any], keys: Tuple[str, ...]) -> Tuple[bool, str]:
    """Return (key_present, text value) for a From/To room reference."""
    params = door.get("params") or {}
    for k in keys:
        if k in params:
            v = _pv(door, k)
            if isinstance(v, dict):
                v = v.get("uid") or v.get("number")
            return True, _txt(v)
    return False, ""


def _is_zero(v: Any) -> bool:
    try:
        return float(v) == 0.0
    except (TypeError, ValueError):
        return False


def _affected(el: Dict[str, Any], **old: Any) -> Dict[str, Any]:
    return {
        "unique_id": el.get("uid"),
        "element_id": el.get("element_id"),
        "label": _label(el),
        "old_values": old,
    }


def _sort_key(e: Dict[str, Any]):
    return (e.get("element_id") or 0, str(e.get("uid")))


class ScheduleConsistencyModule:

    def check_doors_and_rooms(
        self,
        snapshot_id: str = "",
        mark_pattern: str = "",
        suggest_prefix: str = "",
        suggest_digits: int = 3,
        workspace: Any = None,
        **_,
    ) -> Dict[str, Any]:
        elements = self._get_elements(snapshot_id, workspace)
        doors = sorted((e for e in elements if e.get("category") == "OST_Doors"), key=_sort_key)
        rooms = sorted((e for e in elements if e.get("category") == "OST_Rooms"), key=_sort_key)

        regex = None
        if _txt(mark_pattern):
            try:
                regex = re.compile(mark_pattern)
            except re.error as exc:
                raise ValueError(f"mark_pattern is not a valid regular expression: {exc}")

        findings: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []

        def add(check_id: str, severity: str, message: str, affected: List[Dict[str, Any]]) -> None:
            if affected:
                findings.append({
                    "check_id": check_id,
                    "severity": severity,
                    "message": message,
                    "unique_ids": [a["unique_id"] for a in affected],
                    "affected": affected,
                })

        # ---- door marks -------------------------------------------------
        marks: Dict[str, List[Dict[str, Any]]] = {}
        missing_mark: List[Dict[str, Any]] = []
        for d in doors:
            m = _txt(_pv(d, "Mark"))
            if not m:
                missing_mark.append(d)
            else:
                marks.setdefault(m, []).append(d)

        add("door_missing_mark", "warning", "Door has no Mark.",
            [_affected(d, Mark=_pv(d, "Mark")) for d in missing_mark])

        duplicate_extra: List[Dict[str, Any]] = []  # 2nd+ doors sharing a Mark
        for m, group in sorted(marks.items()):
            if len(group) > 1:
                duplicate_extra.extend(group[1:])
                add("door_duplicate_mark", "error",
                    f"{len(group)} doors share the Mark '{m}'.",
                    [_affected(d, Mark=m) for d in group])

        nonconforming: List[Dict[str, Any]] = []
        if regex is None:
            skipped.append({"check_id": "door_mark_pattern_mismatch",
                            "reason": "No mark_pattern supplied; none is assumed."})
        else:
            for m, group in sorted(marks.items()):
                if not regex.fullmatch(m):
                    nonconforming.extend(group)
            add("door_mark_pattern_mismatch", "warning",
                f"Door Mark does not match the pattern '{mark_pattern}'.",
                [_affected(d, Mark=_txt(_pv(d, "Mark"))) for d in nonconforming])

        # ---- rooms ------------------------------------------------------
        by_uid = {r.get("uid"): r for r in rooms}
        by_number: Dict[str, List[Dict[str, Any]]] = {}
        unnumbered: List[Dict[str, Any]] = []
        for r in rooms:
            n = _txt(_pv(r, "Number"))
            if not n:
                unnumbered.append(r)
            else:
                by_number.setdefault(n, []).append(r)
        add("room_missing_number", "warning", "Room has no Number.",
            [_affected(r, Number=_pv(r, "Number")) for r in unnumbered])
        for n, group in sorted(by_number.items()):
            if len(group) > 1:
                add("room_duplicate_number", "error",
                    f"{len(group)} rooms share the Number '{n}'.",
                    [_affected(r, Number=n) for r in group])

        # A blank level_uid ("") is not a placement. If no room in the snapshot
        # carries a level or a location, placement is unknown (not "placed").
        def _has_placement(r: Dict[str, Any]) -> bool:
            return not _blank(r.get("level_uid")) or not _blank(r.get("location"))

        placement_known = any(_has_placement(r) for r in rooms)
        zero = []
        for r in rooms:
            if "Area" in (r.get("params") or {}) and _is_zero(_pv(r, "Area")):
                a = _affected(r, Area=_pv(r, "Area"))
                a["placed"] = _has_placement(r) if placement_known else None
                zero.append(a)
        if zero and not placement_known:
            skipped.append({"check_id": "room_placement_status",
                            "reason": PLACEMENT_UNKNOWN_REASON})
        add("room_zero_area", "error",
            "Room has zero area (not enclosed, too small, or not placed).", zero)

        # ---- door rooms -------------------------------------------------
        have_room_data = any(
            _room_ref(d, FROM_KEYS)[0] or _room_ref(d, TO_KEYS)[0] for d in doors
        )
        if not have_room_data:
            for cid in ("door_missing_room", "door_same_room", "door_in_unnumbered_room"):
                skipped.append({"check_id": cid,
                                "reason": ROOM_DATA_MISSING_REASON})
        else:
            no_room, same, in_unnum = [], [], []
            for d in doors:
                _, frm = _room_ref(d, FROM_KEYS)
                _, to = _room_ref(d, TO_KEYS)
                if not frm or not to:
                    no_room.append(_affected(d, **{"From Room": frm or None, "To Room": to or None}))
                elif frm == to:
                    same.append(_affected(d, **{"From Room": frm, "To Room": to}))
                for side, ref in (("From Room", frm), ("To Room", to)):
                    room = by_uid.get(ref)
                    if room is not None and not _txt(_pv(room, "Number")):
                        in_unnum.append(_affected(d, **{side: ref, "room_unique_id": room.get("uid")}))
            add("door_missing_room", "warning", "Door has no From Room or no To Room.", no_room)
            add("door_same_room", "warning", "Door has the same From Room and To Room.", same)
            add("door_in_unnumbered_room", "warning",
                "Door opens into a room that has no Number.", in_unnum)

        counts: Dict[str, int] = {}
        for f in findings:
            counts[f["check_id"]] = counts.get(f["check_id"], 0) + len(f["affected"])

        total = sum(counts.values())
        room_checks_skipped = [x["check_id"] for x in skipped if x["check_id"].startswith("door_") and x["check_id"] != "door_mark_pattern_mismatch"]
        if total:
            summary = f"{total} problem(s) found across {len(findings)} kind(s) of check."
        else:
            summary = "No problems found by the checks that could run."
        if room_checks_skipped:
            summary += (" The door-to-room checks were NOT run (not enough data: no From Room / To Room "
                        "in this snapshot), so door/room problems may exist that are not shown here.")
        if any(x["check_id"] == "room_placement_status" for x in skipped):
            summary += " Whether zero-area rooms are placed is unknown (no room level or location saved)."

        return {
            "read_only": True,
            "snapshot_id": snapshot_id or "(mock)",
            "doors_checked": len(doors),
            "rooms_checked": len(rooms),
            "total_findings": total,
            "finding_groups": len(findings),
            "summary": summary,
            "counts": counts,
            "skipped": skipped,
            "findings": findings,
            "suggested_marks": self._suggest(
                doors, marks, missing_mark, duplicate_extra, nonconforming,
                suggest_prefix, suggest_digits, regex),
        }

    # -----------------------------------------------------------------------

    def _suggest(self, doors, marks, missing, dup_extra, nonconforming,
                 prefix, digits, regex) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "proposal_only": True,
            "note": "PROPOSAL ONLY. Nothing was changed in the model and no plan was created.",
            "items": [],
        }
        prefix = prefix or ""
        if not prefix.strip():
            out["note"] += " Give suggest_prefix to get proposed Marks."
            return out
        try:
            width = max(1, int(digits))
        except (TypeError, ValueError):
            width = 3

        used = set(marks.keys())  # every existing Mark stays reserved
        targets: Dict[str, Tuple[Dict[str, Any], str]] = {}
        for d in missing:
            targets[d["uid"]] = (d, "missing Mark")
        for d in dup_extra:
            targets.setdefault(d["uid"], (d, "duplicate Mark"))
        for d in nonconforming:
            targets.setdefault(d["uid"], (d, "Mark does not match pattern"))

        order = {d.get("uid"): i for i, d in enumerate(doors)}
        n = 0
        for uid, (d, reason) in sorted(targets.items(), key=lambda kv: order.get(kv[0], 0)):
            while True:
                n += 1
                cand = f"{prefix}{n:0{width}d}"
                if cand not in used:
                    break
            used.add(cand)
            out["items"].append({
                "unique_id": uid,
                "label": _label(d),
                "old_mark": _pv(d, "Mark"),
                "proposed_mark": cand,
                "reason": reason,
                "matches_pattern": (bool(regex.fullmatch(cand)) if regex else None),
            })
        return out

    def _get_elements(self, snapshot_id: str, workspace: Any) -> List[Dict[str, Any]]:
        if not snapshot_id:
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
            require_snapshot_or_mock(snapshot_id, "schedule_consistency")
            snap = generate_mock_snapshot()
            return [el.model_dump(by_alias=True) for el in snap.elements]
        path = workspace.allowed_directories[0] / "snapshots" / f"{snapshot_id}.json"
        if not path.exists():
            raise ValueError(f"Snapshot '{snapshot_id}' not found.")
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("elements", [])
