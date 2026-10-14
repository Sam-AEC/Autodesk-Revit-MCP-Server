"""Tests for the read-only Revit check tools (revit_check_joins, revit_check_intersections,
revit_warnings_delta, revit_check_orientation) and the shared contract / pagination helper.

Nothing here talks to Revit. Three kinds of test:
  * canned script output through a fake bridge (parse, contract, pagination, mock flag, error mapping);
  * the embedded IronPython scripts executed under CPython against a tiny stub of the Revit API
    (``revit_api_stub``), which checks their control flow and the line protocol they print;
  * source guards: the scripts must stay Python 2.7 safe and read-only.
"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import revit_api_stub as stub  # noqa: E402

from revit_mcp_server import check_contract as cc  # noqa: E402
from revit_mcp_server.errors import BridgeError  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MODULE_DIR = PACKAGE_ROOT / "src" / "revit_mcp_server" / "modules" / "revit"
SCRIPTS = sorted((MODULE_DIR / "scripts").glob("*.ipy"))
TOOLS = ("revit_check_joins", "revit_check_intersections", "revit_warnings_delta", "revit_check_orientation")


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("_revit_checks_impl", MODULE_DIR / "module.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod(monkeypatch: pytest.MonkeyPatch) -> Any:
    m = _load_module()
    monkeypatch.setattr(m, "_server_in_mock_mode", lambda: False)  # conftest sets MCP_REVIT_MODE=mock
    return m


@pytest.fixture()
def ws(tmp_path: Path) -> WorkspaceMonitor:
    return WorkspaceMonitor([tmp_path])


class FakeBridge:
    """Stands in for the server's tool executor; records calls and returns canned add-in answers."""

    def __init__(self, output: Optional[str] = None, *, raw: Any = None, exc: Optional[Exception] = None) -> None:
        self.output, self.raw, self.exc = output, raw, exc
        self.calls: List[tuple] = []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        self.calls.append((name, args))
        if self.exc is not None:
            raise self.exc
        if self.raw is not None:
            return self.raw
        return {"success": True, "output": self.output, "error": ""}


class StubBridge:
    """Runs the script the module sends against the Revit API stub, like the add-in would."""

    def __init__(self, document: stub.Document) -> None:
        self.document = document
        self.calls: List[tuple] = []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        self.calls.append((name, args))
        return {"success": True, "output": stub.run_script(args["script"], self.document), "error": ""}


@pytest.fixture()
def revit_stub(monkeypatch: pytest.MonkeyPatch):
    with stub.installed(monkeypatch):
        yield


# --------------------------------------------------------------------------- #
# Parsing and contract
# --------------------------------------------------------------------------- #
CANNED = "\n".join(
    [
        "META\tdoc_title\tVilla.rvt",
        "META\tdoc_guid\tabc-123",
        "garbage line that is not protocol",
        "INFO\tJOIN_DISALLOWED\twall 7 end 1 intended free",
        "FAIL\tJOIN_OPEN\twall 5 end 0 at (1.0, 2.0) m is not joined to any wall",
        "ROW\twall_id=5\tend=0\tstatus=unjoined\tjoined_to=\tx_m=1.0\ty_m=2.0",
        "ROW\twall_id=6\tend=1\tstatus=joined\tjoined_to=7,8\tx_m=3.5\ty_m=2.0",
        "COUNT\tfail\t1",
        "COUNT\tinfo\t1",
        "COUNT\trow\t2",
        "SUMMARY\t4 ends checked on 2 walls, 1 unjoined",
    ]
)


def test_parse_script_output_extracts_fail_lines_rows_and_meta() -> None:
    p = cc.parse_script_output(CANNED)
    assert p.summary == "4 ends checked on 2 walls, 1 unjoined"
    assert p.fails == ["JOIN_OPEN: wall 5 end 0 at (1.0, 2.0) m is not joined to any wall"]
    assert p.infos == ["JOIN_DISALLOWED: wall 7 end 1 intended free"]
    assert p.rows[1] == {"wall_id": "6", "end": "1", "status": "joined", "joined_to": "7,8", "x_m": "3.5", "y_m": "2.0"}
    assert p.meta == {"doc_title": "Villa.rvt", "doc_guid": "abc-123"}
    assert p.counts == {"fail": 1, "info": 1, "row": 2}
    assert p.ignored_lines == 1


def test_parse_accepts_space_separated_fail_lines_and_script_errors() -> None:
    p = cc.parse_script_output("FAIL JOIN_OPEN wall 1\nERROR\tinvalid_input\tgive ids\nCOUNT\tfail\tx")
    assert p.fails == ["JOIN_OPEN wall 1"]
    assert p.errors == [("invalid_input", "give ids")]
    assert p.ignored_lines == 1  # the malformed COUNT


def test_cast_rows_types_and_empty_numbers() -> None:
    rows = cc.cast_rows([{"a": "5", "v": "", "ids": "1,2", "f": "0.25", "s": "x", "b": "true"}], {"a": "int", "v": "float", "ids": "intlist", "f": "float", "b": "bool"})
    assert rows == [{"a": 5, "v": None, "ids": [1, 2], "f": 0.25, "s": "x", "b": True}]


def test_check_joins_returns_the_section_6_contract(mod: Any, ws: WorkspaceMonitor) -> None:
    bridge = FakeBridge(CANNED)
    r = mod.RevitModule().check_joins(tag="T:p3", workspace=ws, tool_executor=bridge)
    assert r["ok"] is True and r["tool"] == "revit_check_joins"
    assert r["summary"] == "4 ends checked on 2 walls, 1 unjoined"
    assert r["fails"] == ["JOIN_OPEN: wall 5 end 0 at (1.0, 2.0) m is not joined to any wall"]
    assert r["info"] == ["JOIN_DISALLOWED: wall 7 end 1 intended free"]
    assert r["document"] == {"title": "Villa.rvt", "guid": "abc-123"}
    assert r["changed_ids"] == [] and r["detail_file"] is None
    assert "mock" not in r and r["verified"] is True
    assert r["limits"]["truncated"] is False and r["limits"]["limit"] == 50
    assert r["counts"] == {"fails": 1, "info": 1, "rows": 2}
    # unjoined ends are listed first and numbers are typed
    assert r["rows"][0]["wall_id"] == 5 and r["rows"][1]["joined_to"] == [7, 8] and r["rows"][1]["x_m"] == 3.5


def test_seam_sends_one_readonly_script_with_injected_args(mod: Any, ws: WorkspaceMonitor) -> None:
    bridge = FakeBridge(CANNED)
    mod.RevitModule().check_joins(ids=[11, 12], tag="T:p3", allow_free_ids=[12], workspace=ws, tool_executor=bridge)
    assert len(bridge.calls) == 1
    name, args = bridge.calls[0]
    assert name == "revit_execute_python" and args["mode"] == "read"
    script = args["script"]
    assert "ARGS = {" in script and "'ids': [11, 12]" in script and "'tag': 'T:p3'" in script
    assert script.index("def select_elements") < script.index("ARGS = {") < script.index("def main")


def test_run_readonly_script_is_the_only_exit_to_revit(mod: Any) -> None:
    seen: List[tuple] = []
    mod.run_readonly_script("x = 1", lambda n, a: seen.append((n, a)) or {"success": True, "output": ""})
    assert seen == [("revit_execute_python", {"script": "x = 1", "mode": "read"})]


# --------------------------------------------------------------------------- #
# Pagination and budgets (1.12)
# --------------------------------------------------------------------------- #
def _many(n: int = 120) -> str:
    lines = [f"FAIL\tINTERSECT\tpair {i}" for i in range(n)]
    lines += [f"ROW\ta_id={i}\tb_id={i + 1}\tvolume_m3={i / 1000}\tstatus=verified" for i in range(n)]
    lines += [f"COUNT\tfail\t{n}", "COUNT\tinfo\t0", f"COUNT\trow\t{n}", "SUMMARY\tmany"]
    return "\n".join(lines)


def test_default_budget_is_at_most_50_rows_and_the_full_list_goes_to_a_file(mod: Any, ws: WorkspaceMonitor) -> None:
    r = mod.RevitModule().check_intersections(set_a={"tag": "T"}, workspace=ws, tool_executor=FakeBridge(_many()))
    assert len(r["fails"]) == 50 and len(r["rows"]) == 50
    assert r["limits"]["truncated"] is True
    assert r["limits"]["fails_total"] == 120 and r["limits"]["rows_total"] == 120
    path = Path(r["detail_file"])
    assert path.is_file() and path.parent.name == "revit_checks"
    path.resolve().relative_to(Path(ws.allowed_directories[0]))  # inside the workspace
    text = path.read_text(encoding="utf-8")
    assert text.count("\nFAIL\t") == 120 and text.count("\nROW\t") == 120


def test_limit_offset_count_only_and_fields(mod: Any, ws: WorkspaceMonitor) -> None:
    m = mod.RevitModule()
    bridge = FakeBridge(_many())
    page2 = m.check_intersections(set_a={"tag": "T"}, limit=10, offset=10, workspace=ws, tool_executor=bridge)
    assert page2["fails"][0].endswith("pair 10") and len(page2["fails"]) == 10 and page2["limits"]["offset"] == 10
    only = m.check_intersections(set_a={"tag": "T"}, count_only=True, workspace=ws, tool_executor=bridge)
    assert only["fails"] == [] and only["info"] == [] and only["rows"] == []
    assert only["counts"]["fails"] == 120 and only["limits"]["count_only"] is True and only["detail_file"] is None
    slim = m.check_intersections(set_a={"tag": "T"}, limit=3, fields=["a_id", "volume_m3"], workspace=ws, tool_executor=bridge)
    assert all(set(row) == {"a_id", "volume_m3"} for row in slim["rows"])
    # rows are ordered by volume, largest first
    assert [row["a_id"] for row in slim["rows"]] == [119, 118, 117]


def test_page_spec_clamps_input() -> None:
    assert cc.PageSpec.from_args() == cc.PageSpec(limit=50, offset=0, count_only=False, fields=None)
    assert cc.PageSpec.from_args(limit=100000).limit == cc.MAX_LIMIT
    assert cc.PageSpec.from_args(limit=0).limit == 1
    assert cc.PageSpec.from_args(limit="bad", offset=-4).offset == 0
    assert cc.PageSpec.from_args(fields=["", " a "]).fields == ("a",)
    assert cc.project_fields([{"a": 1, "b": 2}], None) == [{"a": 1, "b": 2}]
    assert cc.project_fields([{"a": 1, "b": 2}], ["b", "zzz"]) == [{"b": 2}]


def test_script_side_cap_is_reported_as_truncation(mod: Any, ws: WorkspaceMonitor) -> None:
    out = "FAIL\tX\tone\nCOUNT\tfail\t9000\nCOUNT\tinfo\t0\nCOUNT\trow\t0\nSUMMARY\ts"
    r = mod.RevitModule().check_joins(tag="T", workspace=ws, tool_executor=FakeBridge(out))
    assert r["limits"]["truncated"] is True and r["limits"]["script_capped"] is True
    assert r["counts"]["fails"] == 9000 and r["detail_file"] is not None


# --------------------------------------------------------------------------- #
# Mock mode and failures
# --------------------------------------------------------------------------- #
def test_mock_answer_sets_mock_true_at_top_level(mod: Any) -> None:
    mock_raw = {"tool": "revit.execute_python", "mock": True, "result": {"status": "mock-response"}}
    r = mod.RevitModule().check_joins(tag="T", tool_executor=FakeBridge(raw=mock_raw))
    assert r["mock"] is True and r["verified"] is False and r["fails"] == []
    assert "UNVERIFIED" in r["summary"] and "MOCK" in r["summary"]


def test_server_in_mock_mode_never_calls_revit() -> None:
    m = _load_module()  # real _server_in_mock_mode: conftest sets MCP_REVIT_MODE=mock
    bridge = FakeBridge(CANNED)
    for result in (
        m.RevitModule().check_joins(tag="T", tool_executor=bridge),
        m.RevitModule().check_orientation(tag="T", tool_executor=bridge),
        m.RevitModule().check_intersections(set_a={"tag": "T"}, tool_executor=bridge),
        m.RevitModule().warnings_delta(tool_executor=bridge),
    ):
        assert result["mock"] is True and result["verified"] is False
    assert bridge.calls == []


def test_approval_gate_block_is_reported_with_the_seam_hint(mod: Any) -> None:
    exc = BridgeError("Approval mode is enabled. Mutating tool 'revit_execute_python' requires a valid 'plan_id' parameter.")
    r = mod.RevitModule().check_joins(tag="T", tool_executor=FakeBridge(exc=exc))
    assert r["ok"] is False and r["kind"] == "approval_required"
    assert "0.6" in r["hint"] and r["element_ids"] == []


def test_timeout_and_bridge_errors_are_classified(mod: Any) -> None:
    t = mod.RevitModule().check_joins(tag="T", tool_executor=FakeBridge(exc=BridgeError("Bridge error: request timed out")))
    assert t["kind"] == "timeout_running" and "revit_health" in t["hint"]
    b = mod.RevitModule().check_joins(tag="T", tool_executor=FakeBridge(exc=BridgeError("connection refused")))
    assert b["kind"] == "bridge_error"


def test_script_error_unparsable_output_and_missing_executor(mod: Any) -> None:
    m = mod.RevitModule()
    assert m.check_joins(tag="T", tool_executor=FakeBridge(raw={"success": False, "output": "", "error": "NameError: x"}))["kind"] == "script_error"
    assert m.check_joins(tag="T", tool_executor=FakeBridge("nothing useful here"))["kind"] == "unparsable_output"
    assert m.check_joins(tag="T", tool_executor=None)["kind"] == "no_bridge"


def test_script_side_error_lines_become_ok_false(mod: Any) -> None:
    out = "ERROR\tempty_selection\tcheck_joins: no elements matched\nCOUNT\tfail\t0"
    r = mod.RevitModule().check_joins(tag="TYPO", tool_executor=FakeBridge(out))
    assert r["ok"] is False and r["kind"] == "empty_selection" and "Comments" in r["hint"]


def test_bad_arguments_are_rejected_before_anything_is_sent(mod: Any) -> None:
    bridge = FakeBridge(CANNED)
    m = mod.RevitModule()
    assert m.check_joins(ids=["x"], tool_executor=bridge)["kind"] == "invalid_input"
    assert m.check_joins(tag="café", tool_executor=bridge)["kind"] == "invalid_input"
    assert m.check_intersections(set_a={"tag": "T"}, mode="volume", tool_executor=bridge)["kind"] == "invalid_input"
    assert m.check_orientation(tag="T", scope="roofs", tool_executor=bridge)["kind"] == "invalid_input"
    assert m.warnings_delta(baseline_id="../escape", tool_executor=bridge)["kind"] == "invalid_input"
    assert bridge.calls == []


# --------------------------------------------------------------------------- #
# check_intersections on canned output
# --------------------------------------------------------------------------- #
def test_check_intersections_sorts_pairs_by_volume_and_flags_partial(mod: Any, ws: WorkspaceMonitor) -> None:
    out = "\n".join(
        [
            "META\tpartial\t1",
            "FAIL\tINTERSECT\tWalls 1 x Floors 2 overlap 0.0142 m3 at (1.0, 2.0, 3.0) m",
            "INFO\tPARTIAL\tstopped after 20000 bounding-box candidates",
            "ROW\ta_id=1\tb_id=2\tkind=solid\tvolume_m3=0.0142\tstatus=verified",
            "ROW\ta_id=9\tb_id=2\tkind=solid\tvolume_m3=0.9\tstatus=verified",
            "ROW\ta_id=4\tb_id=5\tkind=bbox\tvolume_m3=\tstatus=candidate_no_solid",
            "COUNT\tfail\t1", "COUNT\tinfo\t1", "COUNT\trow\t3", "SUMMARY\tPARTIAL: 3 candidates",
        ]
    )
    r = mod.RevitModule().check_intersections(set_a={"tag": "T"}, set_b={"categories": ["Floors"]}, workspace=ws, tool_executor=FakeBridge(out))
    assert [row["a_id"] for row in r["rows"]] == [9, 1, 4]
    assert r["rows"][2]["volume_m3"] is None
    assert r["limits"]["partial"] is True


# --------------------------------------------------------------------------- #
# The scripts against the Revit API stub
# --------------------------------------------------------------------------- #
def _walls() -> List[stub.Wall]:
    w1 = stub.Wall(101, (0, 0, 0), (10, 0, 0), "T:p3")
    w2 = stub.Wall(102, (10, 0, 0), (10, 10, 0), "T:p3")
    w3 = stub.Wall(103, (10, 10, 0), (0, 10, 0), "T:p3")
    w4 = stub.Wall(104, (0, 10, 0), (0, 0, 0), "T:p3")
    w1.join(1, w2)
    w2.join(0, w1)
    w3.join_allowed[1] = False
    return [w1, w2, w3, w4]


def test_check_joins_script_counts_unjoined_ends(mod: Any, ws: WorkspaceMonitor, revit_stub: None) -> None:
    other = stub.Element(900, stub.Category(stub.BuiltInCategory.OST_Floors, "Floors"), "T:p3")
    document = stub.Document(_walls() + [other])
    r = mod.RevitModule().check_joins(tag="T:p3", allow_free_ids=[104], workspace=ws, tool_executor=StubBridge(document))
    assert r["ok"] is True
    assert r["summary"] == "8 ends checked on 4 walls, 3 unjoined (1 free by join setting, 2 waived)"
    assert len(r["fails"]) == 3 and all(f.startswith("JOIN_OPEN:") for f in r["fails"])
    assert [row["status"] for row in r["rows"]][:3] == ["unjoined"] * 3
    joined = [row for row in r["rows"] if row["status"] == "joined"]
    assert sorted(row["wall_id"] for row in joined) == [101, 102]
    assert all(row["joined_to"] and row["wall_id"] not in row["joined_to"] for row in joined)  # self is ignored
    assert r["document"]["title"] == "Villa.rvt" and r["revit_version"] == "2024"


def test_check_joins_script_reports_selection_problems(mod: Any, revit_stub: None) -> None:
    document = stub.Document(_walls())
    m = mod.RevitModule()
    assert m.check_joins(tool_executor=StubBridge(document))["kind"] == "invalid_input"
    assert m.check_joins(tag="NOPE", tool_executor=StubBridge(document))["kind"] == "empty_selection"
    assert m.check_joins(tag="T", categories=["Spaceships"], tool_executor=StubBridge(document))["kind"] == "invalid_input"
    big = m.check_joins(tag="T:p3", max_elements=2, tool_executor=StubBridge(document))
    assert big["kind"] == "too_many_elements"
    mixed = m.check_joins(ids=[101, 777], tool_executor=StubBridge(document))
    assert mixed["ok"] is True and any("ID_NOT_FOUND" in i for i in mixed["info"])


def _solid_scene() -> stub.Document:
    wall = stub.Element(1, stub.Category(stub.BuiltInCategory.OST_Walls, "Walls"), "T:p3")
    wall.bbox = stub.BoundingBox((0, 0, 0), (10, 1, 10))
    wall.solids = [stub.Solid(10.0)]
    floor = stub.Element(2, stub.Category(stub.BuiltInCategory.OST_Floors, "Floors"), "T:p3")
    floor.bbox = stub.BoundingBox((0, 0, 9), (10, 10, 11))
    floor.solids = [stub.Solid(100.0)]
    column = stub.Element(4, stub.Category(stub.BuiltInCategory.OST_Columns, "Columns"), "T:p3")
    column.bbox = stub.BoundingBox((9, 0, 0), (10, 1, 10))
    column.solids = [stub.Solid(1.0)]
    door = stub.Element(5, stub.Category(stub.BuiltInCategory.OST_Walls, "Doors"), "T:p3")
    door.bbox = stub.BoundingBox((2, 0, 0), (4, 1, 7))
    door.solids = [stub.Solid(1.0)]
    door.Host = wall
    mesh_only = stub.Element(6, stub.Category(stub.BuiltInCategory.OST_Floors, "Floors"), "T:p3")
    mesh_only.bbox = stub.BoundingBox((0, 0, 9.5), (1, 1, 10.5))
    far = stub.Element(3, stub.Category(stub.BuiltInCategory.OST_Walls, "Walls"), "T:p3")
    far.bbox = stub.BoundingBox((100, 100, 0), (110, 101, 10))
    far.solids = [stub.Solid(10.0)]
    stub.BooleanOperationsUtils.overlap = {
        (id(wall.solids[0]), id(floor.solids[0])): 0.5,  # 0.5 ft3 = 0.0142 m3
        (id(column.solids[0]), id(floor.solids[0])): 0.0005,  # 0.0000142 m3, below the default minimum
        (id(door.solids[0]), id(wall.solids[0])): 0.9,  # would be reported if skip_hosted did not apply
    }
    return stub.Document([wall, floor, column, door, mesh_only, far])


def test_check_intersections_script_measures_volumes(mod: Any, ws: WorkspaceMonitor, revit_stub: None) -> None:
    r = mod.RevitModule().check_intersections(
        set_a={"ids": [1, 3, 4]}, set_b={"ids": [2, 6, 5]}, workspace=ws, tool_executor=StubBridge(_solid_scene())
    )
    assert r["ok"] is True
    assert r["fails"] == ["INTERSECT: Walls 1 x Floors 2 overlap 0.014158 m3 at (0.305, 0.61, 0.914) m"]
    assert r["summary"].startswith("3 bounding-box candidates, 2 solid/solid pairs measured among 3 x 3 elements; 1 overlaps >= 0.0005 m3")
    assert "1 candidates without solids" in r["summary"]
    assert [row["a_id"] for row in r["rows"]][0] == 1 and r["rows"][0]["volume_m3"] == 0.014158
    assert any(i.startswith("NO_SOLID:") for i in r["info"])
    assert all(row["a_id"] != 5 for row in r["rows"])  # hosted door vs its wall is skipped
    assert r["limits"]["partial"] is False


def test_check_intersections_script_modes_and_self_test(mod: Any, ws: WorkspaceMonitor, revit_stub: None) -> None:
    m = mod.RevitModule()
    bbox = m.check_intersections(set_a={"ids": [1, 2, 3]}, mode="bbox", workspace=ws, tool_executor=StubBridge(_solid_scene()))
    assert bbox["summary"].startswith("1 bounding-box overlaps among 3 x 3 elements (bounding boxes only")
    assert bbox["fails"][0].startswith("BBOX_OVERLAP: ")
    low = m.check_intersections(set_a={"ids": [1, 2, 4]}, min_volume_m3=0.00001, workspace=ws, tool_executor=StubBridge(_solid_scene()))
    assert len(low["fails"]) == 2  # the column/floor sliver now counts; sorted largest first
    assert low["fails"][0].startswith("INTERSECT: Walls 1") and low["fails"][1].startswith("INTERSECT: Floors 2 x Columns 4")
    partial = m.check_intersections(set_a={"ids": [1, 2, 4]}, max_pairs=1, workspace=ws, tool_executor=StubBridge(_solid_scene()))
    assert partial["limits"]["partial"] is True and partial["summary"].startswith("PARTIAL: ")


def _rooms_scene(with_rooms: bool = True) -> stub.Document:
    into_room = stub.Wall(201, (0, 0, 0), (10, 0, 0), "T:p3", orientation=(0.0, 1.0, 0.0))   # Orientation points into the room
    correct = stub.Wall(202, (0, 10, 0), (10, 10, 0), "T:p3", orientation=(0.0, 1.0, 0.0))   # exterior is outside
    interior = stub.Wall(203, (5, 0, 0), (5, 10, 0), "T:p3", function="Interior", orientation=(1.0, 0.0, 0.0))
    lonely = stub.Wall(204, (50, 50, 0), (60, 50, 0), "T:p3", orientation=(0.0, 1.0, 0.0))  # no room on either side
    elements: List[stub.Element] = [into_room, correct, interior, lonely]
    if with_rooms:
        elements.append(stub.Room(300, (0, 0, 0), (10, 10, 10), "A1"))
    return stub.Document(elements)


def test_check_orientation_script_flags_wall_facing_into_a_room(mod: Any, ws: WorkspaceMonitor, revit_stub: None) -> None:
    r = mod.RevitModule().check_orientation(tag="T:p3", workspace=ws, tool_executor=StubBridge(_rooms_scene()))
    assert r["ok"] is True and r["verified"] is True
    assert r["summary"] == "3 exterior walls probed, 1 facing into a room, 1 unconfirmed (no room on either side)"
    assert len(r["fails"]) == 1 and r["fails"][0].startswith("ORIENT_INTO_ROOM: wall 201") and "Room A1" in r["fails"][0]
    assert any("wall 204" in i for i in r["info"])
    by_wall = {row["wall_id"]: row for row in r["rows"]}
    assert by_wall[201]["status"] == "exterior_in_room" and by_wall[202]["status"] == "ok"
    assert by_wall[201]["exterior_room_id"] == 300 and by_wall[202]["exterior_room_id"] is None
    assert 203 not in by_wall
    everything = mod.RevitModule().check_orientation(tag="T:p3", scope="all", workspace=ws, tool_executor=StubBridge(_rooms_scene()))
    assert any(row["wall_id"] == 203 for row in everything["rows"])


def test_check_orientation_without_rooms_is_unverified(mod: Any, ws: WorkspaceMonitor, revit_stub: None) -> None:
    r = mod.RevitModule().check_orientation(tag="T:p3", workspace=ws, tool_executor=StubBridge(_rooms_scene(with_rooms=False)))
    assert r["ok"] is True and r["verified"] is False and r["fails"] == []
    assert r["summary"].startswith("UNVERIFIED (no rooms)")


def _warning_doc(*failures: stub.Failure, title: str = "Villa.rvt") -> stub.Document:
    wall = stub.Wall(301, (0, 0, 0), (1, 0, 0), "T:p3_walls")
    other = stub.Wall(302, (5, 0, 0), (6, 0, 0), "Other")
    document = stub.Document([wall, other], list(failures))
    document.Title = title
    return document


def test_warnings_delta_snapshot_then_delta(mod: Any, ws: WorkspaceMonitor, revit_stub: None) -> None:
    m = mod.RevitModule()
    overlap = stub.Failure("Highlighted walls overlap.", "Warning", [301, 302])
    enclosed = stub.Failure("Room is not enclosed.", "Warning", [302])
    snap = m.warnings_delta(workspace=ws, tool_executor=StubBridge(_warning_doc(overlap, enclosed)))
    assert snap["ok"] is True and snap["fails"] == []
    base = snap["baseline_id"]
    assert re.fullmatch(r"wb-\d{8}T\d{6}Z-[0-9a-f]{4}", base) and snap["warnings_total"] == 2
    assert Path(snap["baseline_file"]).is_file() and base in snap["summary"]

    off_axis = stub.Failure("Walls are slightly off axis.", "Warning", [301])
    unrelated = stub.Failure("Something else.", "Error", [302])
    after = _warning_doc(overlap, off_axis, unrelated)
    delta = m.warnings_delta(baseline_id=base, tag_prefix="T:p3", workspace=ws, tool_executor=StubBridge(after))
    assert delta["ok"] is True
    assert delta["warnings_delta"] == {"new": 2, "closed": 1}
    assert len(delta["fails"]) == 1 and delta["fails"][0].startswith("NEW_WARNING: Walls are slightly off axis.")
    assert len(delta["info"]) == 1 and "Something else." in delta["info"][0]
    assert delta["summary"].startswith(f"2 new, 1 closed warnings since {base} (was 2, now 3)")
    assert sorted(row["change"] for row in delta["rows"]) == ["closed", "new", "new"]
    assert any(row["ids"] == [301] for row in delta["rows"] if row["change"] == "new")

    no_prefix = m.warnings_delta(baseline_id=base, workspace=ws, tool_executor=StubBridge(after))
    assert len(no_prefix["fails"]) == 2 and no_prefix["info"] == []

    unchanged = m.warnings_delta(baseline_id=base, workspace=ws, tool_executor=StubBridge(_warning_doc(overlap, enclosed)))
    assert unchanged["warnings_delta"] == {"new": 0, "closed": 0} and unchanged["fails"] == []


def test_warnings_delta_refuses_other_documents_and_missing_baselines(mod: Any, ws: WorkspaceMonitor, revit_stub: None) -> None:
    m = mod.RevitModule()
    snap = m.warnings_delta(workspace=ws, tool_executor=StubBridge(_warning_doc()))
    other_doc = _warning_doc(title="Other.rvt")
    other_doc.CreationGUID = "99999999-0000-0000-0000-000000000000"
    mismatch = m.warnings_delta(baseline_id=snap["baseline_id"], workspace=ws, tool_executor=StubBridge(other_doc))
    assert mismatch["ok"] is False and mismatch["kind"] == "document_mismatch"
    missing = m.warnings_delta(baseline_id="wb-nope", workspace=ws, tool_executor=StubBridge(_warning_doc()))
    assert missing["ok"] is False and missing["kind"] == "baseline_not_found"


def test_baseline_needs_a_workspace(mod: Any, revit_stub: None) -> None:
    r = mod.RevitModule().warnings_delta(workspace=None, tool_executor=StubBridge(_warning_doc()))
    assert r["ok"] is False and r["kind"] == "baseline_not_saved"


# --------------------------------------------------------------------------- #
# Source guards: the embedded scripts must stay IronPython 2.7 safe and read-only
# --------------------------------------------------------------------------- #
def _full_script(path: Path) -> str:
    prelude = (MODULE_DIR / "scripts" / "_prelude.ipy").read_text(encoding="utf-8")
    return prelude + "\nARGS = {}\n" + path.read_text(encoding="utf-8")


def test_scripts_exist_and_are_wheel_declared() -> None:
    names = {p.name for p in SCRIPTS}
    assert {"_prelude.ipy", "check_joins.ipy", "check_intersections.ipy", "warnings_dump.ipy", "check_orientation.ipy"} <= names
    import fnmatch
    import tomllib

    patterns = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["package-data"]["revit_mcp_server"]
    base = PACKAGE_ROOT / "src" / "revit_mcp_server"
    for p in SCRIPTS:
        assert any(fnmatch.fnmatch(p.relative_to(base).as_posix(), pat) for pat in patterns), p.name


_PY3_ONLY = tuple(
    getattr(ast, name)
    for name in (
        "AnnAssign", "AsyncFunctionDef", "AsyncFor", "AsyncWith", "Await", "NamedExpr", "JoinedStr", "FormattedValue",
        "Nonlocal", "YieldFrom", "Match", "TryStar", "TypeAlias",
    )
    if hasattr(ast, name)
)
_ALLOWED_IMPORT_ROOTS = {"clr", "System", "Autodesk"}  # json and time are missing in the deployed engine
_READ_ONLY_FORBIDDEN = re.compile(
    r"Transaction|SubTransaction|TransactionGroup|\.Delete\(|\.Set\(|\.SetValue|\.Commit|\.RollBack|\.Regenerate|"
    r"ChangeTypeId|\.Move\(|\.Rotate\(|\.Create\w*\(|\.New\w+\(|\.Copy\w*\(|\.Pin|IFailuresPreprocessor|File\.|Directory\.|open\("
)


def py2_problems(source: str) -> List[str]:
    """Constructs that IronPython 2.7 cannot run (or that the deployed engine lacks), found by AST."""
    tree = ast.parse(source, feature_version=(3, 7))
    problems: List[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, _PY3_ONLY):
            problems.append(f"{type(node).__name__} at line {line}")
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            a = node.args
            if a.kwonlyargs or a.posonlyargs:
                problems.append(f"keyword-only/positional-only arguments at line {line}")
            if isinstance(node, ast.FunctionDef) and (
                node.returns is not None or any(x.annotation is not None for x in a.args + a.kwonlyargs)
            ):
                problems.append(f"annotation at line {line}")
        if isinstance(node, ast.Raise) and node.cause is not None:
            problems.append(f"raise ... from at line {line}")
        if isinstance(node, ast.Dict) and any(k is None for k in node.keys):
            problems.append(f"dict unpacking at line {line}")
        if isinstance(node, (ast.Assign, ast.For, ast.comprehension)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(n, ast.Starred) for t in targets for n in ast.walk(t)):
                problems.append(f"extended unpacking at line {line}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            problems.append(f"print() call at line {line}")
        if isinstance(node, ast.Import):
            problems += [f"import {a.name}" for a in node.names if a.name.split(".")[0] not in _ALLOWED_IMPORT_ROOTS]
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] not in _ALLOWED_IMPORT_ROOTS:
            problems.append(f"from {node.module} import")
    return problems


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_embedded_scripts_are_python_2_compatible_source(path: Path) -> None:
    source = _full_script(path)
    source.encode("ascii")  # plain ASCII source only
    compile(source, path.name, "exec")
    assert py2_problems(source) == [], path.name


@pytest.mark.parametrize(
    "bad",
    [
        'x = f"{1}"',
        "import json",
        "import time",
        "from os import path",
        "def f(a: int): pass",
        "def f(a, *, b): pass",
        "def f():\n    v = 1\n    def g():\n        nonlocal v\n",
        "a, *b = [1, 2]",
        "raise ValueError('x') from None",
        "print('x')",
        "x: int = 1",
        "y = {**{}}",
    ],
)
def test_the_python_2_guard_catches_what_it_should(bad: str) -> None:
    assert py2_problems(bad + "\n"), bad


def test_the_read_only_guard_catches_what_it_should() -> None:
    for bad in ("t = Transaction(doc, 'x')", "doc.Delete(i)", "p.Set(1)", "w.Flip(); doc.Create.NewWall(a)", "f = open('x')"):
        assert _READ_ONLY_FORBIDDEN.search(bad), bad


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_embedded_scripts_cannot_write_to_the_model_or_disk(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    found = _READ_ONLY_FORBIDDEN.findall(code)
    assert not found, f"{path.name} contains write-capable calls: {found}"


@pytest.mark.parametrize("path", [p for p in SCRIPTS if not p.name.startswith("_")], ids=lambda p: p.name)
def test_every_tool_script_ends_with_the_output_protocol(path: Path) -> None:
    assert path.read_text(encoding="utf-8").rstrip().endswith("__output__ = run_main(main)")


def test_built_scripts_parse_with_real_arguments(mod: Any) -> None:
    script = mod.build_script("check_intersections.ipy", {"set_a": {"ids": [1], "tag": "T:p3", "categories": []}, "mode": "solid", "skip_hosted": True, "tolerance_m": 0.0})
    tree = ast.parse(script, feature_version=(3, 7))
    arg_assign = [n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "ARGS"]
    assert len(arg_assign) == 1
    assert ast.literal_eval(arg_assign[0].value)["set_a"]["tag"] == "T:p3"


# --------------------------------------------------------------------------- #
# Registration: module provider, metadata, annotations
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def listed(tmp_path_factory: pytest.TempPathFactory):
    from revit_mcp_server import mcp_server
    from revit_mcp_server.registry_factory import build_registry

    registry, approval, job_manager, _modules, _ws = build_registry(WorkspaceMonitor([Path(tmp_path_factory.mktemp("revit-checks-ws"))]))
    previous = (mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager)
    mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = registry, approval, job_manager
    try:
        tools = {t.name: t for t in asyncio.run(mcp_server.list_tools())}
        gate = {t.name: t for t in registry.get_all_tools()}
        yield tools, gate, mcp_server
    finally:
        mcp_server.registry, mcp_server.approval_provider, mcp_server.job_manager = previous


def test_tools_are_registered_read_only_and_documented(listed: Any) -> None:
    tools, gate, _ = listed
    for name in TOOLS:
        assert name in tools, name
        assert gate[name].is_mutating is False
        ann = tools[name].annotations
        assert ann.readOnlyHint is True and ann.destructiveHint is False and ann.idempotentHint is True
        assert ann.openWorldHint is False
        assert "Read-only" in tools[name].description and len(tools[name].description) > 150
        props = tools[name].inputSchema["properties"]
        assert {"limit", "offset", "count_only", "fields"} <= set(props)
        assert "plan_id" not in props
    assert "revit_check_clashes" in tools["revit_check_intersections"].description
    assert "revit_check_orientation" in tools["revit_check_joins"].description


def test_mock_mode_end_to_end_marks_the_result_as_mock(listed: Any) -> None:
    _, _, mcp_server = listed
    out = asyncio.run(mcp_server.call_tool("revit_check_joins", {"tag": "T:p3"}))[0].text
    assert '"mock": true' in out and '"verified": false' in out and "UNVERIFIED" in out
