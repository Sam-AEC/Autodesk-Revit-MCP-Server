"""Tests for the door/room schedule consistency module (F8)."""
import json
from pathlib import Path

import pytest

from revit_mcp_server.modules.schedule_consistency.module import ScheduleConsistencyModule as Mod

ROOT = Path(__file__).resolve().parents[3]
SEEDED = json.loads((ROOT / "fixtures/canonical-model/seeded-defects.json").read_text(encoding="utf-8"))
SEEDED_COUNTS = {f["rule_id"]: f["expected_count"] for f in SEEDED["expected_findings"]}


class WS:
    def __init__(self, p):
        self.allowed_directories = [p]


def door(i, mark, frm=None, to=None):
    params = {}
    if mark is not None:
        params["Mark"] = {"v": mark}
    if frm is not False:
        params["From Room"] = {"v": frm}
        params["To Room"] = {"v": to}
    return {"uid": f"d{i}", "element_id": i, "category": "OST_Doors", "type_name": "Door", "params": params}


def room(i, number, area=10.0):
    params = {"Area": {"v": area}}
    if number is not None:
        params["Number"] = {"v": number}
    return {"uid": f"r{i}", "element_id": 1000 + i, "category": "OST_Rooms",
            "type_name": f"Room {i}", "level_uid": "L1", "params": params}


def run(tmp_path, elements, **kw):
    snaps = tmp_path / "snapshots"
    snaps.mkdir(exist_ok=True)
    (snaps / "s.json").write_text(json.dumps({"elements": elements}), encoding="utf-8")
    return Mod().check_doors_and_rooms(snapshot_id="s", workspace=WS(tmp_path), **kw)


def test_canonical_fixture_counts(tmp_path):
    # Mirrors seeded-defects.json: 60 doors (12 without Mark), 25 rooms (3 without Number).
    els = [door(i, f"D-{i:03d}" if i < 48 else None, False) for i in range(60)]
    els += [room(i, f"{100 + i}" if i < 22 else None) for i in range(25)]
    res = run(tmp_path, els)
    assert res["counts"]["door_missing_mark"] == SEEDED_COUNTS["door_missing_mark"] == 12
    assert res["counts"]["room_missing_number"] == SEEDED_COUNTS["room_missing_number"] == 3
    assert "door_duplicate_mark" not in res["counts"]
    assert res["read_only"] is True


def test_duplicate_marks_and_old_values(tmp_path):
    res = run(tmp_path, [door(1, "D1", False), door(2, "D1", False), door(3, "D2", False)])
    f = [x for x in res["findings"] if x["check_id"] == "door_duplicate_mark"]
    assert len(f) == 1
    assert f[0]["unique_ids"] == ["d1", "d2"]
    assert f[0]["affected"][0]["old_values"] == {"Mark": "D1"}


def test_room_checks(tmp_path):
    els = [room(1, "101"), room(2, "101"), room(3, None), room(4, "  "), room(5, "105", area=0.0)]
    res = run(tmp_path, els)
    assert res["counts"]["room_duplicate_number"] == 2
    assert res["counts"]["room_missing_number"] == 2
    assert res["counts"]["room_zero_area"] == 1


def test_door_room_checks(tmp_path):
    els = [
        room(1, "101"), room(2, None),
        door(1, "A", "r1", "r1"),          # same room
        door(2, "B", "r1", None),          # missing To
        door(3, "C", "r1", "r2"),          # opens into unnumbered room
        door(4, "D", "101", "r1"),         # fine
    ]
    res = run(tmp_path, els)
    assert res["counts"]["door_same_room"] == 1
    assert res["counts"]["door_missing_room"] == 1
    assert res["counts"]["door_in_unnumbered_room"] == 1


def test_room_checks_skipped_without_room_data(tmp_path):
    res = run(tmp_path, [door(1, "A", False), door(2, "B", False)])
    skipped = {s["check_id"] for s in res["skipped"]}
    assert {"door_missing_room", "door_same_room", "door_in_unnumbered_room"} <= skipped
    assert "door_missing_room" not in res["counts"]


def test_pattern_is_user_supplied_only(tmp_path):
    els = [door(1, "D-001", False), door(2, "X9", False)]
    res = run(tmp_path, els)
    assert any(s["check_id"] == "door_mark_pattern_mismatch" for s in res["skipped"])
    res = run(tmp_path, els, mark_pattern=r"D-\d{3}")
    assert res["counts"]["door_mark_pattern_mismatch"] == 1
    assert res["findings"][-1]["unique_ids"] == ["d2"] or any(
        f["unique_ids"] == ["d2"] for f in res["findings"])


def test_invalid_pattern_rejected(tmp_path):
    with pytest.raises(ValueError, match="regular expression"):
        run(tmp_path, [door(1, "A", False)], mark_pattern="(")


def test_suggestions_are_unique_and_proposal_only(tmp_path):
    els = [door(1, "D-001", False), door(2, "D-001", False), door(3, None, False), door(4, "D-002", False)]
    res = run(tmp_path, els, suggest_prefix="D-", mark_pattern=r"D-\d{3}")
    s = res["suggested_marks"]
    assert s["proposal_only"] is True
    proposed = {i["unique_id"]: i["proposed_mark"] for i in s["items"]}
    assert set(proposed) == {"d2", "d3"}
    assert not set(proposed.values()) & {"D-001", "D-002"}
    assert len(set(proposed.values())) == 2
    assert all(i["matches_pattern"] for i in s["items"])


def test_no_suggestion_without_prefix(tmp_path):
    res = run(tmp_path, [door(1, None, False)])
    assert res["suggested_marks"]["items"] == []


def test_does_not_modify_snapshot(tmp_path):
    els = [door(1, "A", False), door(2, "A", False)]
    run(tmp_path, els, suggest_prefix="A-")
    assert json.loads((tmp_path / "snapshots/s.json").read_text())["elements"] == els


def test_mock_snapshot_runs():
    res = Mod().check_doors_and_rooms()
    assert res["doors_checked"] >= 1 and res["rooms_checked"] == 2
    assert res["counts"]["room_zero_area"] == 1


def test_missing_snapshot(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        Mod().check_doors_and_rooms(snapshot_id="nope", workspace=WS(tmp_path))


def test_total_findings_counts_elements_not_groups(tmp_path):
    els = [door(i, f"D-{i:03d}" if i < 48 else None, False) for i in range(60)]
    els += [room(i, f"{100 + i}" if i < 22 else None) for i in range(25)]
    res = run(tmp_path, els)
    assert res["total_findings"] == 15 == sum(res["counts"].values())
    assert res["finding_groups"] == 2


def test_blank_level_uid_is_not_placed(tmp_path):
    placed = room(1, "101", area=0)
    unplaced = room(2, "102", area=0)
    unplaced["level_uid"] = ""
    res = run(tmp_path, [placed, unplaced])
    by = {a["unique_id"]: a["placed"] for f in res["findings"] if f["check_id"] == "room_zero_area" for a in f["affected"]}
    assert by == {"r1": True, "r2": False}


def test_placement_unknown_when_no_room_has_level(tmp_path):
    r = room(1, "101", area=0)
    r["level_uid"] = ""
    res = run(tmp_path, [r])
    f = next(f for f in res["findings"] if f["check_id"] == "room_zero_area")
    assert f["affected"][0]["placed"] is None
    assert any(s["check_id"] == "room_placement_status" for s in res["skipped"])
    assert "unknown" in res["summary"]


def test_missing_room_data_is_not_a_clean_pass(tmp_path):
    res = run(tmp_path, [door(1, "A", False)])
    assert res["total_findings"] == 0
    assert "NOT run" in res["summary"] and "not enough data" in res["summary"]
    assert all("Not enough data" in s["reason"] for s in res["skipped"] if s["check_id"].startswith("door_") and s["check_id"] != "door_mark_pattern_mismatch")
