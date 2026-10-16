"""revit_cleanup module: manifest, tool metadata, read-mode dispatch, argument validation, verdict and the result contract.

Nothing here talks to Revit. The script runs against a stub of the Revit API in test_revit_cleanup_scripts.py.
Everything that needs a live Revit is UNVERIFIED (see the module docstring).
"""
from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from revit_mcp_server.check_contract import parse_script_output
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest
from revit_mcp_server.modules.revit_cleanup import module as cleanup
from revit_mcp_server.providers.module_provider import ModuleProvider
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.read_mode import ReadModeViolation, validate_read_script
from revit_mcp_server.security.workspace import WorkspaceMonitor
from revit_mcp_server.tool_metadata import enrich_tool

TOOL = "revit_cleanup_audit"
OUTPUT = (
    "SUMMARY\t3 finding(s)\n"
    "META\tdoc_title\tVilla.rvt\nMETA\tdoc_guid\tg-1\nMETA\trevit_version\t2024\n"
    "ROW\tkind=check\tcheck=sheets\tstatus=ran\telapsed_ms=4\tnote=2 sheets read, 1 empty\n"
    "ROW\tkind=check\tcheck=duplicates\tstatus=ran\telapsed_ms=9\tnote=compared\n"
    "ROW\tkind=finding\tcheck=sheets\tcode=SHEETS_EMPTY\tseverity=WARN\tcount=1\tid_total=1\tids=7\tnames=A102 Empty\tnote=sheets with no view\n"
    "ROW\tkind=finding\tcheck=duplicates\tcode=DUPLICATE_ELEMENTS\tseverity=FAIL\tcount=2\tid_total=3\tids=8,9\tnames=Doors (2)\tnote=pairs\n"
    "ROW\tkind=finding\tcheck=sheets\tcode=SHEETS_INFO\tseverity=INFO\tcount=1\tid_total=1\tids=4\tnames=\tnote=fyi\n"
    "ROW\tkind=purge\tgroup=empty_sheets\tcount=3\tids=7\tbasis=no view on the sheet\n"
    "ROW\tkind=warning_type\tcount=5\tids=8,9\tdescription=Walls overlap\n"
    "COUNT\tfail\t0\nCOUNT\trow\t8"
)
ALL_RAN = OUTPUT.replace("ROW\tkind=finding\tcheck=duplicates\tcode=DUPLICATE_ELEMENTS\tseverity=FAIL", "ROW\tkind=finding\tcheck=duplicates\tcode=DUPLICATE_ELEMENTS\tseverity=WARN")


def args(**kw: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(scope=None, checks=["sheets", "duplicates"], max_ids=None, max_purge_ids=None, time_budget_s=None,
                                max_elements=None, tolerance_mm=None, overlap_ratio=None, detail_line_warn=None)
    base.update(kw)
    return cleanup.clean_args(**base)


def manifest() -> Dict[str, Any]:
    return json.loads((cleanup.MODULE_DIR / "module.json").read_text(encoding="utf-8"))


class Canned:
    def __init__(self, output: str = OUTPUT) -> None:
        self.output, self.calls = output, []

    def __call__(self, name: str, a: Dict[str, Any]) -> Any:
        self.calls.append((name, a))
        return {"success": True, "output": self.output, "error": ""}


@pytest.fixture()
def module(monkeypatch):
    monkeypatch.setattr(cleanup, "_server_in_mock_mode", lambda: False)
    return cleanup.RevitCleanupModule()


# --------------------------------------------------------------------------- #
# Manifest and metadata
# --------------------------------------------------------------------------- #
def _undocumented(schema: Any, path: str = "root") -> List[str]:
    missing: List[str] = []
    if isinstance(schema, dict):
        for key, prop in (schema.get("properties") or {}).items():
            if not isinstance(prop, dict) or not prop.get("description"):
                missing.append(f"{path}.{key}")
            missing.extend(_undocumented(prop, f"{path}.{key}"))
        for sub in ("items", "additionalProperties"):
            if isinstance(schema.get(sub), dict):
                missing.extend(_undocumented(schema[sub], f"{path}[{sub}]"))
    return missing


def test_the_manifest_declares_one_read_only_tool_and_documents_every_parameter():
    data = manifest()
    assert data["permissions"] == ["model.read"] and len(data["description"]) < 900
    (cmd,) = data["commands"]
    assert cmd["mcp_tool"] == TOOL and cmd["is_mutating"] is False and "requires_plan" not in cmd
    assert _undocumented(cmd["input_schema"], TOOL) == []
    assert 80 < len(cmd["title"]) < 900
    assert "purge_candidates" in cmd["title"] and "never a claim that removal is safe" in cmd["title"]
    props = cmd["input_schema"]["properties"]
    assert set(props["checks"]["items"]["enum"]) == set(cleanup.CHECKS)
    assert set(props) == {"scope", "checks", "max_ids", "max_purge_ids", "time_budget_s", "max_elements", "tolerance_mm", "overlap_ratio", "detail_line_warn"}


def test_module_files_have_no_conflict_markers():
    for path in sorted(cleanup.MODULE_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".ipy"}:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                assert not re.match(r"^(<{7}|={7}|>{7})( |$)", line), f"{path.name}:{number}"


def wire(tmp_path, monkeypatch, revit=None, mode="ask_first"):
    inst = ModuleInstance(ModuleManifest(**manifest()), cleanup.MODULE_DIR)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    modules = SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False))
    gate = ApprovalGate(tmp_path, mode)
    provider = ModuleProvider(modules, WorkspaceMonitor([tmp_path]))
    capabilities = {tool.name: tool for tool in provider.get_capabilities()}
    capabilities["revit_execute_python"] = SimpleNamespace(is_mutating=True)
    revit = revit or FakeRevit()
    registry = SimpleNamespace(
        lookup_tool=lambda name: capabilities.get(name),
        lookup_tool_provider=lambda name: provider if name in capabilities and name != "revit_execute_python" else revit,
        get_provider=lambda name: SimpleNamespace(gate=gate) if name == "approval" else None,
    )
    provider.tool_registry = registry
    return provider, gate, registry, revit


class FakeRevit:
    def __init__(self, output: str = ALL_RAN) -> None:
        self.output, self.calls = output, []

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return {"success": True, "output": self.output}

    def call_is_read_only(self, name: str, arguments: Dict[str, Any]) -> bool:
        return arguments.get("mode") == "read"


def test_tool_metadata_marks_the_tool_read_only_without_a_plan_id(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    tools = {t.name: t for t in provider.get_capabilities()}
    assert tools[TOOL].is_mutating is False
    enriched = enrich_tool("module", tools[TOOL])
    assert enriched.annotations.readOnlyHint is True and "plan_id" not in enriched.inputSchema["properties"]


def test_the_tool_runs_without_a_plan_in_read_mode_and_the_script_is_valid_read_mode(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    result = asyncio.run(run_gated_tool(registry, gate, TOOL, {"checks": ["sheets"]}))
    assert result["ok"] is True and result["tool"] == TOOL
    assert [c[1]["mode"] for c in revit.calls] == ["read"]
    validate_read_script(revit.calls[0][1]["script"])


def test_a_write_mode_script_would_be_refused_so_the_audit_cannot_slip_a_change_in():
    with pytest.raises(ReadModeViolation):
        validate_read_script(cleanup.build_script(args()) + "\nt = Transaction(doc, 'x')\n")
    for text in ("import os", "from io import open", "x = open('a')"):
        with pytest.raises(ReadModeViolation):
            validate_read_script(cleanup.build_script(args()) + "\n" + text + "\n")


# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #
def test_defaults_and_bounds():
    a = args(checks=None)
    assert a["checks"] == list(cleanup.CHECKS) and a["scope"] == {"mode": "model"}
    assert (a["max_ids"], a["max_purge_ids"], a["time_budget_s"], a["max_elements"]) == (20, 200, 20.0, 150000)
    assert (a["tolerance_mm"], a["overlap_ratio"], a["detail_line_warn"]) == (5.0, 0.9, 500)
    assert args(checks=["duplicates", "sheets"])["checks"] == ["sheets", "duplicates"]  # run order, no duplicates


@pytest.mark.parametrize("bad", [
    dict(checks=[]), dict(checks=["nope"]), dict(checks="sheets"), dict(max_ids=0), dict(max_ids=201), dict(max_ids=1.5),
    dict(max_purge_ids=2001), dict(time_budget_s=0.5), dict(time_budget_s=26), dict(time_budget_s=True), dict(time_budget_s=float("nan")),
    dict(max_elements=10), dict(tolerance_mm=0), dict(overlap_ratio=0.4), dict(overlap_ratio=1.1), dict(detail_line_warn="x"),
    dict(scope="model"), dict(scope={"mode": "all"}), dict(scope={"mode": "categories"}), dict(scope={"mode": "categories", "categories": []}),
    dict(scope={"mode": "categories", "categories": ["Walls'; drop"]}), dict(scope={"mode": "categories", "categories": [1]}),
    dict(scope={"mode": "view"}), dict(scope={"mode": "view", "view_id": "5"}), dict(scope={"mode": "view", "view_id": 0}),
    dict(scope={"mode": "view", "view_id": True}), dict(scope={"mode": "model", "view_id": 5}),
    dict(scope={"mode": "view", "view_id": 5, "categories": ["Walls"]}), dict(scope={"mode": "categories", "categories": ["Walls"], "view_id": 5}),
    dict(scope={"mode": "model", "extra": 1}),
])
def test_bad_arguments_are_refused_before_anything_is_sent(module, bad):
    canned = Canned()
    r = module.cleanup_audit(tool_executor=canned, **bad)
    assert r["ok"] is False and r["kind"] == "invalid_input" and r["hint"] and canned.calls == []


def test_scope_values_reach_the_script_as_python_literals(module):
    canned = Canned()
    module.cleanup_audit(tool_executor=canned, scope={"mode": "categories", "categories": ["Walls", "OST_GenericModel"]}, checks=["duplicates"])
    script = canned.calls[0][1]["script"]
    assert "'categories': ['Walls', 'OST_GenericModel']" in script and canned.calls[0][1]["mode"] == "read"
    compile(script, "cleanup", "exec")


# --------------------------------------------------------------------------- #
# Result contract
# --------------------------------------------------------------------------- #
def test_result_follows_the_section_6_contract(module):
    r = module.cleanup_audit(tool_executor=Canned(), checks=["sheets", "duplicates"])
    assert r["ok"] is True and r["tool"] == TOOL and r["read_only"] is True and r["changed_ids"] == []
    assert r["document"] == {"title": "Villa.rvt", "guid": "g-1"} and r["revit_version"] == "2024"
    assert r["verdict"] == "FAIL" and r["verified"] is True and r["detail_file"] is None
    assert r["summary"].startswith("FAIL: 1 FAIL, 1 WARN, 1 INFO for the whole model; 2 of 2 checks complete")
    assert r["fails"] == ["DUPLICATE_ELEMENTS (2): pairs; ids 8,9 (+1 more)"]
    assert r["warns"] == ["SHEETS_EMPTY (1): sheets with no view; ids 7"]
    assert any(line.startswith("SHEETS_INFO") for line in r["info"])
    assert [f["code"] for f in r["findings"]] == ["DUPLICATE_ELEMENTS", "SHEETS_EMPTY", "SHEETS_INFO"]  # FAIL, WARN, INFO
    dup = r["findings"][0]
    assert dup["count"] == 2 and dup["id_total"] == 3 and dup["element_ids"] == [8, 9] and dup["names"] == ["Doors (2)"]
    assert r["counts"] == {"fails": 1, "warns": 1, "info": 1}
    assert r["warnings_by_type"] == [{"count": 5, "description": "Walls overlap", "element_ids": [8, 9]}]
    assert r["limits"] == {"truncated": False, "partial": False, "max_ids": 20, "max_purge_ids": 200, "ids_capped": True, "time_budget_s": 20.0, "max_elements": 150000}


def test_purge_candidates_are_their_own_field_with_a_note_and_a_basis(module):
    r = module.cleanup_audit(tool_executor=Canned(), checks=["sheets", "duplicates"])
    pc = r["purge_candidates"]
    assert set(pc) == {"note", "total_ids", "groups"} and "deleted nothing" in pc["note"]
    assert pc["groups"] == {"empty_sheets": {"count": 3, "element_ids": [7], "truncated": True, "basis": "no view on the sheet"}}
    assert pc["total_ids"] == 3
    assert "purge candidate ids" in r["summary"] and "nothing was changed" in r["summary"]


@pytest.mark.parametrize("status", ["truncated", "partial", "unreadable", "not_run"])
def test_an_unfinished_check_never_gives_pass(status):
    checks = [{"check": "a", "status": "ran"}, {"check": "b", "status": status}]
    assert cleanup.verdict_of(checks, []) == ("INCOMPLETE", ["b"])
    assert cleanup.verdict_of(checks, [{"severity": "WARN"}])[0] == "INCOMPLETE"
    assert cleanup.verdict_of(checks, [{"severity": "FAIL"}])[0] == "FAIL"


def test_verdicts_pass_warn_fail_and_nothing_ran():
    ran = [{"check": "a", "status": "ran"}, {"check": "s", "status": "skipped"}]
    assert cleanup.verdict_of(ran, []) == ("PASS", [])
    assert cleanup.verdict_of(ran, [{"severity": "INFO"}])[0] == "PASS"
    assert cleanup.verdict_of(ran, [{"severity": "WARN"}])[0] == "WARN"
    assert cleanup.verdict_of(ran, [{"severity": "FAIL"}, {"severity": "WARN"}])[0] == "FAIL"
    assert cleanup.verdict_of([{"check": "s", "status": "skipped"}], [])[0] == "INCOMPLETE"  # nothing ran at all
    assert cleanup.verdict_of([], [])[0] == "INCOMPLETE"


def test_a_check_missing_from_the_script_output_counts_as_not_run(module):
    out = OUTPUT.replace("ROW\tkind=check\tcheck=duplicates\tstatus=ran\telapsed_ms=9\tnote=compared\n", "")
    r = module.cleanup_audit(tool_executor=Canned(out), checks=["sheets", "duplicates"])
    assert {c["check"]: c["status"] for c in r["checks"]} == {"sheets": "ran", "duplicates": "not_run"}
    assert r["verdict"] == "FAIL" and r["verified"] is False and r["limits"]["truncated"] is True


def test_truncated_and_skipped_checks_show_in_summary_and_info(module):
    out = ALL_RAN.replace("check=duplicates\tstatus=ran", "check=duplicates\tstatus=truncated")
    r = module.cleanup_audit(tool_executor=Canned(out), checks=["sheets", "duplicates"])
    assert r["verdict"] == "INCOMPLETE" and r["limits"]["truncated"] is True and r["truncated"] is True and r["verified"] is False
    assert "(not finished: duplicates)" in r["summary"] and any(line.startswith("duplicates truncated:") for line in r["info"])
    skipped = ALL_RAN.replace("check=duplicates\tstatus=ran", "check=duplicates\tstatus=skipped")
    r = module.cleanup_audit(tool_executor=Canned(skipped), checks=["sheets", "duplicates"])
    assert r["verdict"] == "WARN" and "1 outside this scope" in r["summary"] and r["verified"] is True


def test_script_errors_become_input_errors_or_script_errors(module):
    r = module.cleanup_audit(tool_executor=Canned("ERROR\tinvalid_input\tscope.view_id 5 is not a view of this document"))
    assert r["ok"] is False and r["kind"] == "invalid_input" and "scope.view_id" in r["message"]
    r = module.cleanup_audit(tool_executor=Canned("ERROR\tscript_exception\tNameError: x"))
    assert r["kind"] == "script_exception" and "read-only" in r["hint"]
    r = module.cleanup_audit(tool_executor=Canned("garbage"))
    assert r["ok"] is False and r["kind"] == "unparsable_output"
    r = module.cleanup_audit(tool_executor=lambda n, a: {"success": False, "error": "boom"})
    assert r["kind"] == "script_error" and "unchanged" in r["hint"]


def test_bridge_problems_and_modes(module, monkeypatch):
    def raise_timeout(name, a):
        raise RuntimeError("request timed out")

    assert module.cleanup_audit(tool_executor=raise_timeout)["kind"] == "timeout_running"

    def raise_other(name, a):
        raise RuntimeError("pipe closed")

    assert module.cleanup_audit(tool_executor=raise_other)["kind"] == "bridge_error"
    assert module.cleanup_audit()["kind"] == "no_bridge"
    running = module.cleanup_audit(tool_executor=lambda n, a: {"status": "running", "request_id": "r-1"})
    assert running["status"] == "running" and running["request_id"] == "r-1" and running["verified"] is False and running["verdict"] == "INCOMPLETE"
    mocked = module.cleanup_audit(tool_executor=lambda n, a: {"mock": True})
    assert mocked["mock"] is True and mocked["verified"] is False and mocked["verdict"] == "INCOMPLETE" and "UNVERIFIED" in mocked["summary"]
    monkeypatch.setattr(cleanup, "_server_in_mock_mode", lambda: True)
    canned = Canned()
    again = module.cleanup_audit(tool_executor=canned)
    assert again["mock"] is True and again["purge_candidates"]["groups"] == {} and canned.calls == []


def test_the_script_text_is_what_the_parser_expects():
    parsed = parse_script_output(OUTPUT)
    assert not parsed.errors and parsed.ignored_lines == 0 and len([r for r in parsed.rows if r["kind"] == "finding"]) == 3
