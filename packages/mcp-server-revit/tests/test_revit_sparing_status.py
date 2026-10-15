"""revit_sparing approval status tools: read (get, summary), set with a transition table, and the setup of the parameter.

The scripts run against the Revit API stub (tests/revit_sparing_stub.py). That proves control flow, the transition rules,
refusals that change nothing, rollback and read-back, not that Revit accepts the same calls (UNVERIFIED in a live Revit).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_api_stub as base  # noqa: E402
import revit_sparing_stub as ss  # noqa: E402
from revit_mcp_server.modules.revit_sparing import module as sp  # noqa: E402
from test_revit_sparing_scripts import Env, build_scene, why  # noqa: E402

@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "_server_in_mock_mode", lambda: False)
    with ss.installed_sparing(monkeypatch) as world:
        yield Env(world, build_scene(world), tmp_path)


LABEL = {"proposed": "Voorstel", "requested": "Aangevraagd", "approved": "Akkoord", "rejected": "Afgewezen", "built": "Gebouwd"}
STATUS = "Sparing status"


def get(env, **args):
    return env.module.status_get(tool_executor=env.bridge, workspace=env.ws, **args)


def summary(env, **args):
    return env.module.status_summary(tool_executor=env.bridge, workspace=env.ws, **args)


def set_status(env, **args):
    return env.module.status_set(approved_executor=env.bridge, workspace=env.ws, **args)


def setup(env, **args):
    return env.module.status_setup(approved_executor=env.bridge, workspace=env.ws, **args)


def placed(env) -> Dict[str, Any]:
    """Four sparingen placed with status Voorstel; returns them by crossing id."""
    env.w.family(800, "Sparing")
    r = env.place()
    assert r["ok"] is True, why(r)
    return {e.entity.values["key"][len("sparing:"):]: e for e in env.owned()}


def value(e) -> str:
    return e.named[STATUS].value


def by_crossing(result) -> Dict[str, Dict[str, Any]]:
    return {r["crossing_id"]: r for r in result["rows"]}


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #
def test_status_get_reads_every_sparing_with_discipline_and_status(env):
    made = placed(env)
    before = env.w.snapshot()
    r = get(env)
    assert r["ok"] is True and r["verified"] is True, why(r)
    assert list(r)[:5] == ["ok", "tool", "verified", "summary", "totals"] and list(r)[-1] == "rows"
    assert r["totals"]["selected"] == 4 and r["totals"]["by_status"] == {"proposed": 4}
    rows = by_crossing(r)
    assert set(rows) == set(made)
    pipe, duct = rows["301x101"], rows["302x101"]
    assert (pipe["id"], pipe["kind"], pipe["tag"], pipe["status"], pipe["raw"]) == (made["301x101"].Id.Value, "sparing_family", "SPA-L00", "proposed", "Voorstel")
    assert (pipe["discipline"], pipe["mep_cat"], pipe["host_cat"], pipe["host_id"]) == ("piping", "pipes", "walls", 101)
    assert (duct["discipline"], duct["family"], duct["type"]) == ("hvac", "Sparing", "Standaard")
    assert pipe["has_param"] is True and pipe["writable"] is True
    assert r["transitions"]["approved"] == ["built", "rejected"] and r["status_labels"] == LABEL
    assert "setup" not in r and env.bridge.modes[-1] == "read"
    assert env.w.snapshot() == before


def test_status_get_reports_a_missing_parameter_honestly_and_creates_nothing(env):
    env.w.family(800, "Sparing", instance_params={"b": (0.1, "Double", False), "h": (0.1, "Double", False), "d": (0.1, "Double", False)})
    assert env.place(status_parameter=None)["ok"] is True
    r = get(env)
    assert r["ok"] is True and r["totals"]["without_param"] == 4 and r["totals"]["by_status"] == {"no_parameter": 4}
    assert r["setup"]["needed"] is True and r["setup"]["sparingen_without_parameter"] == 4
    assert r["setup"]["exists_in_project"] is False and "revit_sparing_status_setup" in r["setup"]["next_step"]
    assert "Nothing was created" in r["setup"]["next_step"]
    assert any("STATUS_PARAMETER_MISSING" in i for i in r["info"])
    assert {x["has_param"] for x in r["rows"]} == {False}
    assert env.w.ParameterBindings.items == [] and env.w.file_writes == []


def test_status_get_unknown_and_unset_texts_and_the_filter(env):
    made = placed(env)
    made["301x101"].named[STATUS].value = ""
    made["302x101"].named[STATUS].value = "akkoord"  # case does not count
    made["303x201"].named[STATUS].value = "misschien"
    r = get(env)
    rows = by_crossing(r)
    assert (rows["301x101"]["status"], rows["302x101"]["status"], rows["303x201"]["status"]) == ("unset", "approved", "unknown")
    assert rows["303x201"]["raw"] == "misschien" and any("STATUS_UNKNOWN" in i for i in r["info"])
    only = get(env, only_status=["unset", "unknown"])
    assert sorted(x["crossing_id"] for x in only["rows"]) == ["301x101", "303x201"] and only["totals"]["filtered_out"] == 2
    assert [x["crossing_id"] for x in get(env, only_status=["Akkoord"])["rows"]] == ["302x101"]


def test_status_get_family_name_reaches_sparingen_this_module_did_not_place(env):
    sym = env.w.family(800, "Sparing")
    foreign = env.w.put(ss.SInstance(950, sym, ss.ft((500, 9000, 500))))
    foreign.named[STATUS].value = "Akkoord"
    r = get(env, family_name="Sparing")
    (row,) = r["rows"]
    assert (row["id"], row["kind"], row["status"], row["crossing_id"], row["discipline"]) == (950, "foreign", "approved", "", "unknown")
    assert get(env)["rows"] == []  # not tagged: not one of ours
    assert get(env, ids=[950, 999])["totals"]["selected"] == 1


def test_status_get_levels_hosts_and_a_discipline_parameter(env):
    made = placed(env)
    made["303x201"].LevelId = base.ElementId(11)
    made["303x201"].named["Discipline"] = ss.rs.Param(made["303x201"], "Discipline", "Sanitair", "String")
    r = get(env, discipline_parameter="Discipline")
    rows = by_crossing(r)
    assert rows["303x201"]["level"] == "00 begane grond" and rows["303x201"]["discipline"] == "Sanitair"
    assert rows["301x101"]["discipline"] == "piping"


def test_status_summary_counts_by_status_discipline_and_level(env):
    made = placed(env)
    made["301x101"].named[STATUS].value = "Akkoord"
    made["303x201"].named[STATUS].value = "Akkoord"
    made["303x201"].LevelId = base.ElementId(11)
    r = summary(env)
    assert r["ok"] is True and r["totals"]["by_status"] == {"proposed": 2, "approved": 2}
    assert [(x["status"], x["count"]) for x in r["rows"]] == [("proposed", 2), ("approved", 2)]
    r = summary(env, group_by=["status", "discipline"])
    assert {(x["status"], x["discipline"]): x["count"] for x in r["rows"]} == {
        ("proposed", "hvac"): 1, ("proposed", "piping"): 1, ("approved", "piping"): 2}
    r = summary(env, group_by=["level", "host_category"])
    assert {(x["level"], x["host_category"]): x["count"] for x in r["rows"]} == {("00 begane grond", "floors"): 1, ("(none)", "walls"): 3}
    assert r["totals"]["group_by"] == ["level", "host_category"] and r["counts"]["rows"] == 2


def test_status_summary_says_when_the_parameter_is_missing(env):
    env.w.family(800, "Sparing", instance_params={"b": (0.1, "Double", False), "h": (0.1, "Double", False), "d": (0.1, "Double", False)})
    assert env.place(status_parameter=None)["ok"] is True
    r = summary(env)
    assert r["totals"]["by_status"] == {"no_parameter": 4} and r["setup"]["needed"] is True


# --------------------------------------------------------------------------- #
# Set
# --------------------------------------------------------------------------- #
def test_set_moves_along_the_table_and_reads_back(env):
    made = placed(env)
    ids = [e.Id.Value for e in made.values()]
    r = set_status(env, ids=ids, status="requested")
    assert r["ok"] is True and r["verified"] is True, why(r)
    assert {value(e) for e in made.values()} == {"Aangevraagd"}
    assert sorted(r["changed_ids"]) == sorted(ids) and r["totals"]["set"] == 4
    assert r["post_check"]["ok"] is True and r["post_check"]["checked"] == 4
    assert all(c["check"].endswith("status read back") for c in r["post_check"]["checks"])
    assert {(x["from"], x["to"], x["action"]) for x in r["rows"]} == {("proposed", "requested", "set")}
    log = env.w.txn_log
    assert len([x for x in log if x[0] == "commit" and x[1].startswith("Status ")]) == 4 and ("group_assimilate", "AEC sparing status") in log
    assert env.bridge.modes[-1] == "write"
    r = set_status(env, changes=[{"id": made["301x101"].Id.Value, "status": "approved"}, {"id": made["302x101"].Id.Value, "status": "Afgewezen"}])
    assert r["ok"] is True, why(r)
    assert (value(made["301x101"]), value(made["302x101"]), value(made["303x201"])) == ("Akkoord", "Afgewezen", "Aangevraagd")
    r = set_status(env, ids=[made["301x101"].Id.Value], status="built")
    assert r["ok"] is True and value(made["301x101"]) == "Gebouwd"


def test_set_refuses_an_illegal_move_for_the_whole_call_and_changes_nothing(env):
    made = placed(env)
    before = env.w.snapshot()
    ids = [e.Id.Value for e in made.values()]
    r = set_status(env, ids=ids, status="approved")
    assert r["ok"] is False and r["kind"] == "illegal_transition", why(r)
    assert "proposed -> approved is not allowed (from proposed: requested)" in r["message"]
    assert sorted(r["element_ids"]) == sorted(ids) and r["changed_ids"] == []
    assert r["transitions"]["proposed"] == ["requested"] and "step by step" in r["hint"]
    assert env.w.snapshot() == before and {value(e) for e in made.values()} == {"Voorstel"}
    assert env.w.txn_log == [x for x in env.w.txn_log if not x[1].startswith("Status")]
    # one bad move in a mixed list stops the legal ones too
    r = set_status(env, changes=[{"id": made["301x101"].Id.Value, "status": "requested"}, {"id": made["302x101"].Id.Value, "status": "built"}])
    assert r["kind"] == "illegal_transition" and r["element_ids"] == [made["302x101"].Id.Value]
    assert value(made["301x101"]) == "Voorstel"
    # built is the end of the line, rejected goes back to proposed only
    made["303x201"].named[STATUS].value = "Gebouwd"
    r = set_status(env, ids=[made["303x201"].Id.Value], status="proposed")
    assert r["kind"] == "illegal_transition" and "no further status" in r["message"]


def test_set_same_status_is_not_a_change_and_unset_may_only_become_proposed(env):
    made = placed(env)
    r = set_status(env, ids=[made["301x101"].Id.Value], status="proposed")
    assert r["ok"] is True and r["changed_ids"] == [] and r["totals"]["set"] == 0 and "already" in r["summary"]
    assert [x for x in env.w.txn_log if x[1].startswith("Status")] == []
    made["301x101"].named[STATUS].value = ""
    r = set_status(env, ids=[made["301x101"].Id.Value], status="requested")
    assert r["kind"] == "illegal_transition" and "unset -> requested" in r["message"]
    r = set_status(env, ids=[made["301x101"].Id.Value], status="proposed")
    assert r["ok"] is True and value(made["301x101"]) == "Voorstel"


def test_set_refuses_unknown_stored_text_missing_parameter_and_unknown_ids(env):
    made = placed(env)
    made["301x101"].named[STATUS].value = "misschien"
    r = set_status(env, ids=[made["301x101"].Id.Value], status="requested")
    assert r["kind"] == "illegal_transition" and "'misschien' is none of the status labels" in r["message"]
    r = set_status(env, ids=[999999], status="requested")
    assert r["kind"] == "element_not_found" and r["element_ids"] == [999999]
    made["302x101"].named[STATUS].IsReadOnly = True
    r = set_status(env, ids=[made["302x101"].Id.Value], status="requested")
    assert r["kind"] == "missing_parameter" and "revit_sparing_status_setup" in r["message"] and "Nothing was changed" in r["hint"]
    r = set_status(env, ids=[made["302x101"].Id.Value], status="requested", status_parameter="Bestaat niet")
    assert r["kind"] == "missing_parameter" and "Bestaat niet" in r["message"] and "Sparing status" in r["message"]


def test_set_scope_form_with_from_status_and_custom_labels(env):
    made = placed(env)
    made["301x101"].named[STATUS].value = "Aangevraagd"
    r = set_status(env, tag="SPA-L00", status="approved", from_status=["requested"])
    assert r["ok"] is True, why(r)
    assert (value(made["301x101"]), value(made["302x101"])) == ("Akkoord", "Voorstel")
    r = set_status(env, tag="SPA-L00", status="requested", from_status=["proposed"], status_labels={"requested": "In behandeling"})
    assert r["ok"] is True and value(made["302x101"]) == "In behandeling"
    r = get(env, status_labels={"requested": "In behandeling"})
    assert by_crossing(r)["302x101"]["status"] == "requested"
    assert set_status(env, tag="NIETS", status="requested")["summary"].startswith("nothing to change")


def test_set_dry_run_does_everything_then_rolls_back(env):
    made = placed(env)
    before = env.w.snapshot()
    values = {k: value(e) for k, e in made.items()}
    r = set_status(env, ids=[e.Id.Value for e in made.values()], status="requested", dry_run=True)
    assert r["ok"] is True and r["dry_run"] is True and r["outcome"] == "dry_run" and r["verified"] is False, why(r)
    assert r["summary"].startswith("DRY RUN") and r["changed_ids"] == [] and sorted(r["would_change_ids"]) == sorted(e.Id.Value for e in made.values())
    assert r["post_check"]["ok"] is True and r["post_check"]["checked"] == 4
    assert {k: value(e) for k, e in made.items()} == values and env.w.snapshot() == before
    assert ("group_rollback", "AEC sparing status") in env.w.txn_log


def test_set_commit_failure_rolls_everything_back_with_the_ids(env):
    made = placed(env)
    ids = [e.Id.Value for e in made.values()]
    env.w.commit_failures["Status %d to requested" % ids[2]] = [base.Failure("Element is pinned", "Error", [])]
    r = set_status(env, ids=ids, status="requested")
    assert r["ok"] is False and r["kind"] == "rolled_back" and "Element is pinned" in r["message"], why(r)
    assert ids[2] in r["element_ids"] and r["changed_ids"] == []
    assert {value(e) for e in made.values()} == {"Voorstel"}
    r = set_status(env, ids=ids, status="requested", on_error="skip")
    assert r["ok"] is False and r["kind"] == "partial_failure" and len(r["changed_ids"]) == 3


def test_set_read_back_mismatch_is_never_ok(env):
    made = placed(env)
    e = made["301x101"]

    class Stubborn(ss.rs.Param):
        def AsString(self):  # a parameter that does not keep what is written
            return "Voorstel"

    e.named[STATUS] = Stubborn(e, STATUS, "Voorstel", "String")
    r = set_status(env, ids=[e.Id.Value], status="requested")
    assert r["ok"] is False and r["kind"] == "rolled_back" and "status read back" in r["message"]


# --------------------------------------------------------------------------- #
# Setup of the shared parameter
# --------------------------------------------------------------------------- #
def shared_file(env, path="C:/Firm/shared.txt", active=True):
    f = env.w.shared_files[path] = ss.SDefFile(env.w)
    if active:
        env.w.app.SharedParametersFilename = path
    return f


def test_setup_without_a_shared_parameter_file_is_refused_and_changes_nothing(env):
    r = setup(env)
    assert r["ok"] is False and r["kind"] == "shared_parameter_file_missing", why(r)
    assert "Manage > Shared Parameters" in r["message"] and env.w.ParameterBindings.items == [] and env.w.file_writes == []


def test_setup_creates_the_definition_binds_it_and_restores_the_file_setting(env):
    f = shared_file(env, active=False)
    env.w.app.SharedParametersFilename = "C:/Other/mine.txt"
    r = setup(env, shared_parameter_file="C:/Firm/shared.txt")
    assert r["ok"] is True and r["verified"] is True, why(r)
    assert env.w.app.SharedParametersFilename == "C:/Other/mine.txt"  # the user's own setting is back
    assert env.w.file_writes == [("group", "AEC Sparing"), ("definition", STATUS)]
    assert [d.Name for d in f.Groups[0].Definitions] == [STATUS]
    (definition, binding), = env.w.ParameterBindings.items
    assert definition.Name == STATUS and [c.Name for c in binding.Categories] == ["Generic Models"]
    assert r["post_check"]["ok"] is True and r["rows"][0]["action"] == "bound"
    assert any("SHARED_PARAMETER_FILE_WRITTEN" in i and "does not remove" in i for i in r["info"])
    assert env.w.txn_log[-1] == ("group_assimilate", "AEC sparing status parameter")
    # the read tool now sees the parameter as bound
    placed(env)
    g = get(env, status_parameter=STATUS)
    assert g["ok"] is True and "setup" not in g  # the family has its own parameter of that name
    # a second call finds everything in place and writes nothing
    env.w.file_writes.clear()
    r = setup(env, shared_parameter_file="C:/Firm/shared.txt")
    assert r["ok"] is True and r["rows"][0]["action"] == "already_bound" and env.w.file_writes == [] and "nothing to do" in r["summary"]


def test_setup_uses_an_existing_definition_and_extends_the_categories(env):
    f = shared_file(env)
    g = ss.SDefGroup(env.w, "Firma")
    g.Definitions.append(ss.SDefinition(STATUS))
    f.Groups.append(g)
    r = setup(env, group_name="Firma")
    assert r["ok"] is True and env.w.file_writes == [], why(r)
    r = setup(env, group_name="Firma", categories=["genericmodels", "specialtyequipment", "wallopenings"])
    assert r["ok"] is True and r["rows"][0]["action"] == "extended", why(r)
    assert any("CATEGORY_SKIPPED" in i and "Rectangular Straight Wall Openings" in i for i in r["info"])
    (_, binding), = env.w.ParameterBindings.items
    assert sorted(c.Name for c in binding.Categories) == ["Generic Models", "Specialty Equipment"]


def test_setup_dry_run_writes_nothing_neither_file_nor_model(env):
    shared_file(env)
    r = setup(env, dry_run=True)
    assert r["ok"] is True and r["dry_run"] is True and r["verified"] is False, why(r)
    assert env.w.file_writes == [] and env.w.ParameterBindings.items == []
    assert r["rows"][0]["action"] == "would_create_definition" and "not undone by a rollback" in r["summary"]
    # with the definition already in the file the dry run really binds, then rolls the binding back
    f = env.w.shared_files["C:/Firm/shared.txt"]
    g = ss.SDefGroup(env.w, "AEC Sparing")
    g.Definitions.append(ss.SDefinition(STATUS))
    f.Groups.append(g)
    r = setup(env, dry_run=True)
    assert r["ok"] is True and r["dry_run"] is True and r["post_check"]["ok"] is True and env.w.ParameterBindings.items == []
    assert ("group_rollback", "AEC sparing status parameter") in env.w.txn_log


def test_setup_bind_failure_rolls_back_and_says_so(env):
    shared_file(env)
    env.w.fail_on["bind_insert"] = lambda n: True
    r = setup(env)
    assert r["ok"] is False and r["kind"] == "rolled_back" and "Revit refused bind_insert" in r["message"]
    assert env.w.ParameterBindings.items == []
    env.w.fail_on.clear()
    env.w.categories.clear()
    r = setup(env)
    assert r["kind"] == "no_bindable_category"


# --------------------------------------------------------------------------- #
# Arguments are checked before anything is sent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("call,args,needle", [
    ("status_get", {"status_labels": {"approved": "Voorstel"}}, "must differ"),
    ("status_get", {"status_labels": {"built": "approved"}}, "key of another status"),
    ("status_get", {"status_labels": {"klaar": "x"}}, "unknown keys"),
    ("status_get", {"status_labels": "Akkoord"}, "must be an object"),
    ("status_get", {"only_status": ["maybe"]}, "unknown status"),
    ("status_get", {"max_elements": 9999}, "max_elements"),
    ("status_get", {"ids": [1, 1]}, "twice"),
    ("status_get", {"tag": "café"}, "tag is required"),
    ("status_summary", {"group_by": ["colour"]}, "unknown field"),
    ("status_summary", {"group_by": "status"}, "list"),
    ("status_set", {}, "say which sparingen"),
    ("status_set", {"ids": [1]}, "status is required"),
    ("status_set", {"ids": [1], "status": "done"}, "unknown status"),
    ("status_set", {"ids": [1], "tag": "A", "status": "built"}, "not both"),
    ("status_set", {"ids": [1], "changes": [{"id": 2, "status": "built"}]}, "own status per id"),
    ("status_set", {"changes": [{"id": 2}]}, "unknown status"),
    ("status_set", {"changes": [{"id": 2, "status": "built"}, {"id": 2, "status": "built"}]}, "twice"),
    ("status_set", {"changes": [{"id": 2, "status": "built", "x": 1}]}, "id and status only"),
    ("status_set", {"tag": "A", "status": "built", "max_changes": 0}, "max_changes"),
    ("status_set", {"ids": [1], "status": "built", "from_status": ["approved"]}, "only filters"),
    ("status_set", {"tag": "A", "status": "built", "on_error": "retry"}, "on_error"),
    ("status_set", {"tag": "A", "status": "built", "dry_run": "yes"}, "true or false"),
    ("status_setup", {"categories": ["doors"]}, "unknown category"),
    ("status_setup", {"shared_parameter_file": "C:/x/params.docx"}, ".txt"),
    ("status_setup", {"shared_parameter_file": "C:/x/<a>.txt"}, ".txt"),
    ("status_setup", {"group_name": "a|b"}, "not allow"),
])
def test_bad_status_arguments_are_refused_before_anything_is_sent(env, call, args, needle):
    sent = len(env.bridge.scripts)
    r = {"status_get": get, "status_summary": summary, "status_set": set_status, "status_setup": setup}[call](env, **args)
    assert r["ok"] is False and r["kind"] == "invalid_input" and needle in r["message"], r
    assert len(env.bridge.scripts) == sent


def test_transition_table_is_closed_and_every_status_is_reachable():
    assert set(sp.TRANSITIONS) == set(sp.STATUS_KEYS) == set(sp.DEFAULT_LABELS)
    assert all(set(v) <= set(sp.STATUS_KEYS) for v in sp.TRANSITIONS.values())
    reachable = {n for v in sp.TRANSITIONS.values() for n in v} | set(sp.FROM_UNSET)
    assert reachable == set(sp.STATUS_KEYS)
    assert sp.TRANSITIONS["built"] == []
