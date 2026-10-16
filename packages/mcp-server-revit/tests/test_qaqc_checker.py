"""Tests for Phase 10 — QA/QC Checker module (W7, W9)."""
import importlib.util
import pytest
from pathlib import Path
from revit_mcp_server.semantic.engine import generate_mock_snapshot


def _load_mod(relpath: str, name: str):
    p = Path(__file__).parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_qaqc = _load_mod("src/revit_mcp_server/modules/qaqc_checker/module.py", "_qaqc_impl")
QaqcCheckerModule = _qaqc.QaqcCheckerModule


class MockWorkspace:
    def __init__(self, tmp_path: Path):
        self.allowed_directories = [tmp_path]


@pytest.fixture
def workspace(tmp_path):
    return MockWorkspace(tmp_path)


@pytest.fixture
def module():
    return QaqcCheckerModule()


@pytest.fixture
def snap_and_ws(tmp_path):
    ws = MockWorkspace(tmp_path)
    snap = generate_mock_snapshot()
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{snap.snapshot_id}.json"
    with open(snap_path, "w", encoding="utf-8") as f:
        f.write(snap.model_dump_json(by_alias=True, indent=2))
    return snap, ws


# --- Rule listing ---

def test_list_rules_core(module):
    result = module.list_rules(rule_pack="core")
    assert result["rules_count"] >= 10
    rule_ids = {r["id"] for r in result["rules"]}
    assert "room_not_placed" in rule_ids
    assert "door_missing_mark" in rule_ids
    assert "room_missing_number" in rule_ids


# --- Run check ---

def test_run_check_mock_snapshot(module, workspace):
    result = module.run_check(workspace=workspace)
    assert "total_findings" in result
    assert result["rules_run"] >= 10
    assert "by_severity" in result
    assert "error" in result["by_severity"]
    assert "warning" in result["by_severity"]
    assert "info" in result["by_severity"]
    # Check structure of findings
    for f in result["findings"]:
        assert "rule_id" in f
        assert "severity" in f
        assert "message" in f


def test_run_check_detects_unplaced_room(module, workspace):
    result = module.run_check(workspace=workspace)
    findings_by_rule = {f["rule_id"] for f in result["findings"]}
    # Mock snapshot has 1 unplaced room
    assert "room_not_placed" in findings_by_rule


def test_run_check_detects_missing_room_name(module, workspace):
    result = module.run_check(workspace=workspace)
    findings_by_rule = {f["rule_id"] for f in result["findings"]}
    # Mock snapshot rooms have no Name parameter → room_missing_name fires
    assert "room_missing_name" in findings_by_rule


def test_run_check_with_snapshot(module, snap_and_ws):
    snap, ws = snap_and_ws
    result = module.run_check(snapshot_id=snap.snapshot_id, workspace=ws)
    assert result["total_findings"] >= 1


# --- Issue store ---

def test_issues_persist_after_run(module, workspace):
    module.run_check(workspace=workspace)
    issues = module.list_issues(workspace=workspace)
    assert issues["total"] >= 1
    assert all("rule_id" in i for i in issues["issues"])
    assert all("status" in i for i in issues["issues"])
    assert all(i["status"] == "open" for i in issues["issues"])


def test_filter_issues_by_severity(module, workspace):
    module.run_check(workspace=workspace)
    errors = module.list_issues(severity="error", workspace=workspace)
    warnings = module.list_issues(severity="warning", workspace=workspace)
    assert all(i["severity"] == "error" for i in errors["issues"])
    assert all(i["severity"] == "warning" for i in warnings["issues"])


def test_resolve_issue(module, workspace):
    module.run_check(workspace=workspace)
    all_issues = module.list_issues(workspace=workspace)
    
    if not all_issues["issues"]:
        pytest.skip("No issues generated from mock snapshot")
    
    issue_id = all_issues["issues"][0]["id"]
    res = module.resolve_issue(issue_id=issue_id, workspace=workspace)
    assert res["status"] == "resolved"
    
    # Verify
    resolved = module.list_issues(status="resolved", workspace=workspace)
    assert any(i["id"] == issue_id for i in resolved["issues"])


def test_second_run_resolves_fixed_issues(module, workspace):
    """Running check twice with the same snapshot should keep issues open (not resolve them)."""
    module.run_check(workspace=workspace)
    first_count = module.list_issues(status="open", workspace=workspace)["total"]
    
    module.run_check(workspace=workspace)
    second_count = module.list_issues(status="open", workspace=workspace)["total"]
    
    # Same defects → same open count
    assert first_count == second_count


def test_resolve_nonexistent_issue_raises(module, workspace):
    # Ensure DB exists first
    module.run_check(workspace=workspace)
    with pytest.raises(ValueError, match="not found"):
        module.resolve_issue(issue_id="does-not-exist", workspace=workspace)


def test_run_check_without_snapshot_rejected_in_bridge_mode(module, workspace, monkeypatch):
    from revit_mcp_server.config import BridgeMode, config

    monkeypatch.setattr(config, "mode", BridgeMode.bridge)
    with pytest.raises(ValueError, match="requires a snapshot_id"):
        module.run_check(snapshot_id="", workspace=workspace)


# --- Shareable rule packs ---

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_PACK = REPO_ROOT / "rule_packs" / "examples" / "door-room-basics.yaml"

VALID_PACK = """rules:
  - id: door_mark_missing
    severity: warning
    description: "Door has no Mark."
    filter:
      category: OST_Doors
      parameter: {name: Mark, empty: true}
    assertion: "element_count == 0"
"""


def _write(ws, rel, text):
    p = ws.allowed_directories[0] / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_example_pack_is_valid_and_ships(module, workspace):
    ws_copy = _write(workspace, "door-room-basics.yaml", EXAMPLE_PACK.read_text(encoding="utf-8"))
    result = module.validate_rule_pack(path=str(ws_copy), workspace=workspace)
    assert result["valid"], result["errors"]
    assert result["rules_count"] == 3


def test_builtin_core_pack_validates(module, workspace):
    assert module.validate_rule_pack(rule_pack="core", workspace=workspace)["valid"]


def test_validate_reports_actionable_errors_per_rule(module, workspace):
    p = _write(workspace, "bad.yaml", """rules:
  - id: ok_rule
    severity: error
    description: fine
    filter: {category: OST_Doors}
  - id: ok_rule
    severity: fatal
    filter:
      regex: "^D-"
      parameter: {name: Mark}
    assertion: "something else"
  - severity: error
""")
    r = module.validate_rule_pack(path=str(p), workspace=workspace)
    assert not r["valid"]
    msgs = [(e["rule_id"], e["field"], e["message"]) for e in r["errors"]]
    assert any(f == "id" and "Duplicate" in m for _, f, m in msgs)
    assert any(f == "severity" and "one of" in m for _, f, m in msgs)
    assert any(f == "description" for _, f, _ in msgs)
    assert any(f == "filter.regex" and "Unknown filter operator" in m for _, f, m in msgs)
    assert any(f == "filter.parameter" and "exactly one" in m for _, f, m in msgs)
    assert any(f == "assertion" and "Unknown assertion" in m for _, f, m in msgs)
    assert any(f == "id" and rid == "rules[2]" for rid, f, _ in msgs)


def test_validate_handles_non_yaml_and_wrong_shape(module, workspace):
    assert not module.validate_rule_pack(path=str(_write(workspace, "a.yaml", "rules: [")), workspace=workspace)["valid"]
    assert not module.validate_rule_pack(path=str(_write(workspace, "b.yaml", "- 1\n- 2\n")), workspace=workspace)["valid"]
    assert not module.validate_rule_pack(path=str(_write(workspace, "c.yaml", "rules: []\n")), workspace=workspace)["valid"]


def test_validate_does_not_execute_python_tags(module, workspace):
    p = _write(workspace, "evil.yaml", "rules: !!python/object/apply:os.system ['echo hi']\n")
    r = module.validate_rule_pack(path=str(p), workspace=workspace)
    assert not r["valid"]


def test_validate_rejects_path_outside_workspace(module, workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "x.yaml"
    outside.write_text(VALID_PACK, encoding="utf-8")
    with pytest.raises(Exception, match="outside the allowed workspace"):
        module.validate_rule_pack(path=str(outside), workspace=workspace)


def test_import_then_list_and_run_check_with_user_pack(module, workspace):
    src = _write(workspace, "incoming/firm.yaml", VALID_PACK)
    res = module.import_rule_pack(source_path=str(src), workspace=workspace)
    assert res["status"] == "imported"
    dest = workspace.allowed_directories[0] / "rule_packs" / "firm.yaml"
    assert dest.read_text(encoding="utf-8") == VALID_PACK

    packs = {p["name"]: p for p in module.list_rule_packs(workspace=workspace)["packs"]}
    assert packs["core"]["source"] == "builtin"
    assert packs["firm"]["source"] == "user" and packs["firm"]["valid"]

    assert module.list_rules(rule_pack="firm", workspace=workspace)["rules_count"] == 1
    result = module.run_check(rule_pack="firm", workspace=workspace)
    assert result["rule_pack"] == "firm"
    assert result["rules_run"] == 1


def test_import_refuses_invalid_pack(module, workspace):
    src = _write(workspace, "bad.yaml", "rules:\n  - id: x\n    severity: nope\n")
    with pytest.raises(ValueError, match="invalid"):
        module.import_rule_pack(source_path=str(src), workspace=workspace)
    assert not (workspace.allowed_directories[0] / "rule_packs" / "bad.yaml").exists()


def test_import_refuses_overwrite_unless_flag(module, workspace):
    src = _write(workspace, "firm.yaml", VALID_PACK)
    module.import_rule_pack(source_path=str(src), workspace=workspace)
    with pytest.raises(ValueError, match="overwrite=true"):
        module.import_rule_pack(source_path=str(src), workspace=workspace)
    assert module.import_rule_pack(source_path=str(src), overwrite=True, workspace=workspace)["status"] == "imported"


def test_import_refuses_builtin_name_and_bad_names(module, workspace):
    src = _write(workspace, "core.yaml", VALID_PACK)
    with pytest.raises(ValueError, match="built-in"):
        module.import_rule_pack(source_path=str(src), overwrite=True, workspace=workspace)
    for bad in ("../evil", "a/b", "..", ".hidden", "x" * 80):
        with pytest.raises(ValueError, match="Invalid rule pack name"):
            module.import_rule_pack(source_path=str(src), name=bad, workspace=workspace)


def test_import_rejects_source_outside_workspace(module, workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside2") / "x.yaml"
    outside.write_text(VALID_PACK, encoding="utf-8")
    with pytest.raises(Exception, match="outside the allowed workspace"):
        module.import_rule_pack(source_path=str(outside), workspace=workspace)
    traversal = workspace.allowed_directories[0] / ".." / outside.parent.name / "x.yaml"
    with pytest.raises(Exception, match="outside the allowed workspace"):
        module.import_rule_pack(source_path=str(traversal), workspace=workspace)


def test_run_check_rejects_traversal_pack_names(module, workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside3") / "evil.yaml"
    outside.write_text(VALID_PACK, encoding="utf-8")
    for bad in (str(outside), "../evil", "rule_packs/../../evil", "..\\evil"):
        with pytest.raises(ValueError, match="Invalid rule pack name"):
            module.run_check(rule_pack=bad, workspace=workspace)


def test_run_check_unknown_pack_and_invalid_user_pack(module, workspace):
    with pytest.raises(ValueError, match="not found"):
        module.run_check(rule_pack="nope", workspace=workspace)
    _write(workspace, "rule_packs/broken.yaml", "rules:\n  - id: x\n")
    with pytest.raises(ValueError, match="invalid"):
        module.run_check(rule_pack="broken", workspace=workspace)


def test_user_pack_cannot_shadow_builtin(module, workspace):
    _write(workspace, "rule_packs/core.yaml", VALID_PACK)
    assert module.list_rules(rule_pack="core", workspace=workspace)["rules_count"] >= 10


def test_export_builtin_and_user_pack(module, workspace):
    res = module.export_rule_pack(rule_pack="core", workspace=workspace)
    out = workspace.allowed_directories[0] / "exports" / "core.yaml"
    assert out.is_file() and res["rules_count"] >= 10
    with pytest.raises(ValueError, match="overwrite=true"):
        module.export_rule_pack(rule_pack="core", workspace=workspace)
    module.export_rule_pack(rule_pack="core", overwrite=True, workspace=workspace)

    _write(workspace, "rule_packs/firm.yaml", VALID_PACK)
    dest = workspace.allowed_directories[0] / "share"
    dest.mkdir()
    module.export_rule_pack(rule_pack="firm", destination=str(dest), workspace=workspace)
    assert (dest / "firm.yaml").read_text(encoding="utf-8") == VALID_PACK


def test_export_rejects_destination_outside_workspace(module, workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside4")
    with pytest.raises(Exception, match="outside the allowed workspace"):
        module.export_rule_pack(rule_pack="core", destination=str(outside / "core.yaml"), workspace=workspace)
    traversal = workspace.allowed_directories[0] / ".." / outside.name / "core.yaml"
    with pytest.raises(Exception, match="outside the allowed workspace"):
        module.export_rule_pack(rule_pack="core", destination=str(traversal), workspace=workspace)
    assert not (outside / "core.yaml").exists()
    with pytest.raises(ValueError, match="Invalid rule pack name"):
        module.export_rule_pack(rule_pack="../core", workspace=workspace)


def test_symlinked_user_pack_escaping_workspace_is_refused(module, workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside5") / "evil.yaml"
    outside.write_text(VALID_PACK, encoding="utf-8")
    link = workspace.allowed_directories[0] / "rule_packs" / "link.yaml"
    link.parent.mkdir()
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(Exception, match="outside the allowed workspace"):
        module.run_check(rule_pack="link", workspace=workspace)
    assert "link" not in {p["name"] for p in module.list_rule_packs(workspace=workspace)["packs"]}


def test_heijmans_derived_pack_is_valid():
    import yaml


    pack = REPO_ROOT / "rule_packs" / "heijmans-derived.yaml"
    result = _qaqc._validate_pack_data(yaml.safe_load(pack.read_text(encoding="utf-8")))
    assert result["errors"] == [] and result["rules_count"] == 5


def test_naming_check_reads_type_names_with_ename():
    # Live (Revit 2024): `type.Name` raised in IronPython, the script returned '' and every one of 13809 walls was
    # reported as off pattern.
    source = (REPO_ROOT / "packages" / "mcp-server-revit" / "src" / "revit_mcp_server" / "modules" / "revit" / "scripts"
              / "check_naming_and_params.ipy").read_text(encoding="utf-8")
    assert "str(ename(el))" in source and "str(el.Name)" not in source
