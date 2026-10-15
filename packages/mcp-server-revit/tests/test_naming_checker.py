"""Tests for the naming_checker module (checks names against a user-supplied convention)."""
import json
from pathlib import Path

import pytest

from revit_mcp_server.modules.naming_checker import module as _nc
from revit_mcp_server.modules.naming_checker.module import NamingCheckerModule
from revit_mcp_server.semantic.engine import generate_mock_snapshot

CONVENTION = {
    "pattern": "{project}-{originator}-{level}-{number}",
    "fields": {
        "project": {"allowed": ["PRJ1"]},
        "originator": {"allowed": ["ABC", "XYZ"]},
        "level": ["00", "01"],
        "number": {"regex": "[0-9]{4}"},
    },
}


class MockWorkspace:
    def __init__(self, tmp_path: Path):
        self.allowed_directories = [tmp_path]


@pytest.fixture
def module():
    return NamingCheckerModule()


def _one(module, name, convention=CONVENTION, kind="file_names"):
    res = module.check_names(convention=convention, names={kind: [name]})
    assert res["summary"]["checked"] == 1
    return res["results"][0]


def test_pass(module):
    res = module.check_names(
        convention=CONVENTION,
        names={"file_names": ["PRJ1-ABC-00-0001", "PRJ1-XYZ-01-1234"]},
    )
    assert res["summary"] == {"checked": 2, "passed": 2, "failed": 0, "not_checked": 0}
    assert res["results"][0]["fields"]["originator"] == "ABC"
    assert res["by_kind"]["file_names"]["passed"] == 2
    assert "ISO 19650" in res["disclaimer"]  # says it does NOT check against it


@pytest.mark.parametrize(
    "name,field",
    [
        ("BAD1-ABC-00-0001", "project"),
        ("PRJ1-QQQ-00-0001", "originator"),
        ("PRJ1-ABC-09-0001", "level"),
        ("PRJ1-ABC-00-12", "number"),
    ],
)
def test_each_field_failure(module, name, field):
    r = _one(module, name)
    assert r["passed"] is False
    assert [f["field"] for f in r["failures"]] == [field]
    assert r["failures"][0]["reason"]


def test_multiple_field_failures_and_counts(module):
    res = module.check_names(
        convention=CONVENTION,
        names={"file_names": ["PRJ1-ABC-00-0001", "NOPE-QQQ-00-0001"]},
    )
    assert res["summary"]["failed"] == 1
    assert res["failures_by_field"] == {"project": 1, "originator": 1}


def test_wrong_structure_gives_part_count_hint(module):
    r = _one(module, "PRJ1-ABC-0001")
    assert r["failures"][0]["field"] == "(whole name)"
    assert "4 parts" in r["failures"][0]["reason"]


def test_spaces_and_empty_name(module):
    assert _one(module, " PRJ1-ABC-00-0001")["failures"][0]["reason"].startswith("has spaces")
    assert _one(module, "")["failures"][0]["reason"] == "is empty"


def test_empty_field_value(module):
    r = _one(module, "PRJ1--00-0001")
    assert [f["field"] for f in r["failures"]] == ["originator"]
    assert r["failures"][0]["reason"] == "is empty"


def test_ignore_case_and_length_rules(module):
    conv = {
        "pattern": "{a}_{b}",
        "fields": {
            "a": {"allowed": ["Wall"], "ignore_case": True},
            "b": {"min_length": 2, "max_length": 3},
        },
    }
    assert _one(module, "WALL_ab", conv)["passed"]
    assert not _one(module, "Wall_a", conv)["passed"]
    assert not _one(module, "Wall_abcd", conv)["passed"]
    assert not _one(module, "Floor_ab", conv)["passed"]


def test_adjacent_fixed_length_fields(module):
    conv = {"pattern": "{a}{b}", "fields": {"a": {"length": 2}, "b": {"regex": "[0-9]+"}}}
    assert _one(module, "AB123", conv)["passed"]
    assert _one(module, "AB12x", conv)["failures"][0]["field"] == "b"


@pytest.mark.parametrize(
    "conv,fragment",
    [
        ({"pattern": "", "fields": {}}, "needs a 'pattern'"),
        ({"fields": {}}, "needs a 'pattern'"),
        ({"pattern": "no fields here", "fields": {}}, "no {field}"),
        ({"pattern": "{a}-{b", "fields": {"a": {}, "b": {}}}, "unmatched"),
        ({"pattern": "{a}-{}", "fields": {"a": {}}}, "invalid field name"),
        ({"pattern": "{a}-{a}", "fields": {"a": {}}}, "same field twice"),
        ({"pattern": "{a}-{b}", "fields": {"a": {}}}, "No rules given"),
        ({"pattern": "{a}", "fields": {"a": {}, "z": {}}}, "not in the pattern"),
        ({"pattern": "{a}{b}", "fields": {"a": {}, "b": {}}}, "next to each other"),
        ({"pattern": "{a}", "fields": {"a": {"regex": "(["}}}, "regex is not valid"),
        ({"pattern": "{a}", "fields": {"a": {"allowed": []}}}, "nothing could ever pass"),
        ({"pattern": "{a}", "fields": {"a": {"colour": "red"}}}, "unknown settings"),
        ({"pattern": "{a b}", "fields": {"a b": {}}}, "invalid field name"),
        ({"by_kind": {"nonsense": {"pattern": "{a}", "fields": {"a": {}}}}}, "Unknown kind"),
    ],
)
def test_bad_pattern_is_rejected_with_plain_message(module, conv, fragment):
    with pytest.raises(ValueError) as exc:
        module.check_names(convention=conv, names={"file_names": ["x"]})
    assert fragment in str(exc.value)


def test_missing_convention_is_rejected(module):
    with pytest.raises(ValueError, match="no built-in convention"):
        module.check_names(names={"file_names": ["x"]})


def test_unknown_kind_rejected(module):
    with pytest.raises(ValueError, match="Unknown kind"):
        module.check_names(convention=CONVENTION, names={"room_names": ["x"]})


def test_empty_input(module):
    res = module.check_names(convention=CONVENTION)
    assert res["summary"] == {"checked": 0, "passed": 0, "failed": 0, "not_checked": 0}
    assert res["results"] == []
    assert any("nothing was checked" in n for n in res["notes"])
    res = module.check_names(convention=CONVENTION, names={"file_names": []})
    assert res["summary"]["checked"] == 0


def test_unicode_names(module):
    conv = {
        "pattern": "{zone}-{name}",
        "fields": {"zone": {"allowed": ["Ünïcode", "東京"]}, "name": {"regex": r"\w+"}},
    }
    assert _one(module, "東京-ビル", conv)["passed"]
    # decomposed (NFD) input is normalised, so it still matches the composed value
    assert _one(module, "Ünı̈code-Åäö".replace("nı̈", "nï"), conv)["passed"] is True
    r = _one(module, "Москва-дом", conv)
    assert r["failures"][0]["field"] == "zone"
    assert "Москва" in r["failures"][0]["reason"]


def test_by_kind_and_skipped_kinds(module):
    conv = {"by_kind": {"level_names": {"pattern": "L{n}", "fields": {"n": {"regex": "[0-9]{2}"}}}}}
    res = module.check_names(
        convention=conv,
        names={"level_names": ["L01", "Level 1"], "view_names": ["whatever"]},
    )
    assert res["summary"] == {"checked": 2, "passed": 1, "failed": 1, "not_checked": 1}
    assert any("view names not checked" in n for n in res["notes"])


def test_kinds_filter(module):
    res = module.check_names(
        convention=CONVENTION,
        names={"file_names": ["bad"], "view_names": ["bad"]},
        kinds=["view_names"],
    )
    assert list(res["by_kind"]) == ["view_names"]


def test_example_files_are_labelled_and_valid(module):
    listing = module.list_example_conventions()
    names = {e["name"] for e in listing["examples"]}
    assert names == {"example_file_names", "example_sheets_views_levels"}
    for e in listing["examples"]:
        assert e["label"].startswith("EXAMPLE ONLY")
        assert e["covers"]
    for name in names:
        data = module._load_convention_file(name, None)
        _nc._parse_conventions(data)  # does not raise


def test_example_file_checks(module):
    res = module.check_names(
        convention_file="example_file_names",
        names={"file_names": ["PRJ1-ABC-ZZ-00-M3-A-0001", "PRJ1-ABC-ZZ-00-M3-Q-0001"]},
    )
    assert res["summary"]["passed"] == 1
    assert res["results"][1]["failures"][0]["field"] == "role"

    res = module.check_names(
        convention_file="example_sheets_views_levels",
        names={
            "sheet_numbers": ["A-GA-101", "A-GA-1"],
            "sheet_names": ["Architecture - Ground floor plan"],
            "view_names": ["WORK_L01_Plan"],
            "level_names": ["L01", "Level 1"],
            "grid_names": ["A", "12", "AA"],
        },
    )
    assert res["summary"]["checked"] == 9
    assert res["summary"]["failed"] == 3


def test_convention_file_in_workspace_and_traversal(module, tmp_path):
    ws = MockWorkspace(tmp_path)
    (tmp_path / "mine.json").write_text(json.dumps(CONVENTION), encoding="utf-8")
    res = module.check_names(convention_file="mine.json", names={"file_names": ["PRJ1-ABC-00-0001"]}, workspace=ws)
    assert res["summary"]["passed"] == 1
    with pytest.raises(ValueError, match="inside the workspace"):
        module.check_names(convention_file="../outside.json", names={"file_names": ["x"]}, workspace=ws)


def test_snapshot_names(module, tmp_path):
    ws = MockWorkspace(tmp_path)
    snap = generate_mock_snapshot()
    snap.source.doc_title = "PRJ1-ABC-00-0001"
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / f"{snap.snapshot_id}.json").write_text(
        snap.model_dump_json(by_alias=True), encoding="utf-8"
    )
    conv = {
        "by_kind": {
            "file_names": CONVENTION,
            "level_names": {"pattern": "Level {n}", "fields": {"n": {"regex": "[0-9]"}}},
        }
    }
    res = module.check_names(convention=conv, snapshot_id=snap.snapshot_id, workspace=ws)
    assert res["by_kind"]["file_names"]["passed"] == 1
    assert res["by_kind"]["level_names"] == {"checked": 2, "passed": 2, "failed": 0}
    with pytest.raises(ValueError, match="not found"):
        module.check_names(convention=conv, snapshot_id="missing", workspace=ws)
    with pytest.raises(ValueError, match="not found"):
        module.check_names(convention=conv, snapshot_id="../x", workspace=ws)


def _snap(tmp_path, elements, source=None, sid="s1"):
    (tmp_path / "snapshots").mkdir(exist_ok=True)
    (tmp_path / "snapshots" / f"{sid}.json").write_text(
        json.dumps({"snapshot_id": sid, "source": source or {}, "elements": elements}), encoding="utf-8")
    return sid


def _view(uid, name, key="View Name"):
    return {"uid": uid, "category": "OST_Views", "type_name": "Drafting View", "params": {key: {"v": name}}}


VIEW_CONV = {"pattern": "{a}_{b}", "fields": {"a": {"allowed": ["WORK"]}, "b": {}}}


def test_snapshot_views_are_not_a_clean_pass(module, tmp_path):
    sid = _snap(tmp_path, [_view("v1", "WORK_Plan")])
    res = module.check_names(convention=VIEW_CONV, snapshot_id=sid, kinds=["view_names"],
                             workspace=MockWorkspace(tmp_path))
    assert res["summary"]["passed"] == 1
    assert res["complete"] is False
    assert res["by_kind"]["view_names"]["complete"] is False
    assert res["not_enough_data"][0]["kind"] == "view_names"
    assert "drafting views" in res["not_enough_data"][0]["reason"]


def test_snapshot_without_views_says_not_enough_data(module, tmp_path):
    sid = _snap(tmp_path, [])
    res = module.check_names(convention=VIEW_CONV, snapshot_id=sid, kinds=["view_names"],
                             workspace=MockWorkspace(tmp_path))
    assert res["complete"] is False and "no views at all" in res["not_enough_data"][0]["reason"]


def test_views_declared_complete_are_trusted(module, tmp_path):
    sid = _snap(tmp_path, [_view("v1", "WORK_Plan")], source={"views_complete": True})
    res = module.check_names(convention=VIEW_CONV, snapshot_id=sid, kinds=["view_names"],
                             workspace=MockWorkspace(tmp_path))
    assert res["complete"] is True and res["not_enough_data"] == []


def test_localised_labels_are_found_via_aliases(module, tmp_path):
    sid = _snap(tmp_path, [_view("v1", "WORK_Plan", key="Ansichtsname")], source={"views_complete": True})
    res = module.check_names(convention=VIEW_CONV, snapshot_id=sid, kinds=["view_names"],
                             workspace=MockWorkspace(tmp_path))
    assert res["results"][0]["name"] == "WORK_Plan" and res["results"][0]["passed"]
    assert res["complete"] is True


def test_unknown_label_is_reported_not_skipped_silently(module, tmp_path):
    sheet = {"uid": "s", "category": "OST_Sheets", "params": {"Zzz": {"v": "A101"}}}
    sid = _snap(tmp_path, [sheet])
    conv = {"pattern": "{a}", "fields": {"a": {}}}
    res = module.check_names(convention=conv, snapshot_id=sid, kinds=["sheet_numbers"],
                             workspace=MockWorkspace(tmp_path))
    assert res["summary"]["checked"] == 0
    assert res["complete"] is False
    assert "none of the known parameter labels" in res["not_enough_data"][0]["reason"]


def test_type_name_substitution_is_reported(module, tmp_path):
    lvl = {"uid": "l", "category": "OST_Levels", "type_name": "Level 1", "params": {}}
    sid = _snap(tmp_path, [lvl])
    conv = {"pattern": "Level {n}", "fields": {"n": {}}}
    res = module.check_names(convention=conv, snapshot_id=sid, kinds=["level_names"],
                             workspace=MockWorkspace(tmp_path))
    assert res["summary"]["checked"] == 1
    assert any("type name was checked instead" in r["reason"] for r in res["not_enough_data"])


def test_split_honours_field_regex():
    conv = {"pattern": "{a}-{b}", "fields": {"a": {"regex": "[a-z]+-[a-z]+"}, "b": {"regex": "[a-z]+"}}}
    m = NamingCheckerModule()
    r = m.check_names(convention=conv, names={"file_names": ["foo-bar-baz"]})
    assert r["results"][0]["passed"] is True
    assert r["results"][0]["fields"] == {"a": "foo-bar", "b": "baz"}


def test_split_honours_length_constraints():
    conv = {"pattern": "{a}-{b}", "fields": {"a": {"min_length": 5}, "b": {"max_length": 3}}}
    m = NamingCheckerModule()
    r = m.check_names(convention=conv, names={"file_names": ["ab-cd-ef", "ab-cd"]})
    assert r["results"][0]["passed"] is True and r["results"][0]["fields"]["a"] == "ab-cd"
    assert r["results"][1]["passed"] is False
