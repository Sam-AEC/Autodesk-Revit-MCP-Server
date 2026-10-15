"""revit_recipes module: the recipe library, its approval binding and its standing approvals.

Nothing here talks to Revit: a stub transport answers revit_execute_python and records every script it is sent.
Everything that needs a live Revit is UNVERIFIED (see the module docstring and docs/recipes-library.md).
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import human_approve  # noqa: E402
from revit_mcp_server import approve_cli  # noqa: E402
from revit_mcp_server.errors import BridgeError  # noqa: E402
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest  # noqa: E402
from revit_mcp_server.modules.revit_recipes import module as recipes  # noqa: E402
from revit_mcp_server.providers.module_provider import ModuleProvider  # noqa: E402
from revit_mcp_server.security.approval import ApprovalGate  # noqa: E402
from revit_mcp_server.security.dispatch import run_gated_tool  # noqa: E402
from revit_mcp_server.security.read_mode import ReadModeViolation, validate_read_script  # noqa: E402
from revit_mcp_server.security.recipe_store import (  # noqa: E402
    RecipeError,
    RecipeStore,
    code_sha256,
    validate_param_schema,
    validate_params,
    validate_recipe_id,
)
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402

SAVE, LIST, GET, RUN, DELETE = ("revit_recipe_save", "revit_recipe_list", "revit_recipe_get", "revit_recipe_run", "revit_recipe_delete")

READ_CODE = "def main():\n    summary('read ok')\n    row([('n', 1)])\n\n\n__output__ = run_main(main)\n"
WRITE_CODE = (
    "def main():\n    t = Transaction(doc, 'recipe')\n    t.Start()\n    t.Commit()\n    meta('changed_ids', '5,6')\n"
    "    summary('wrote')\n\n\n__output__ = run_main(main)\n"
)
READ_OUT = "SUMMARY\tread ok\nROW\tn=1\nCOUNT\tfail\t0\nCOUNT\trow\t1"
WRITE_OUT = "SUMMARY\twrote\nMETA\tchanged_ids\t5,6\nMETA\tverified\t1\nCOUNT\tfail\t0\nCOUNT\trow\t0"
SCHEMA = [
    {"name": "width", "type": "number", "unit": "mm", "min": 100, "max": 5000, "required": True},
    {"name": "label", "type": "string", "default": "A", "max_length": 20},
    {"name": "count", "type": "integer", "min": 1, "max": 10, "default": 3},
    {"name": "flag", "type": "boolean", "default": False},
    {"name": "kind", "type": "string", "enum": ["wall", "floor"], "default": "wall"},
]


class FakeRevit:
    """Stub transport for revit_execute_python; records (name, arguments)."""

    def __init__(self, read_output: str = READ_OUT, write_output: str = WRITE_OUT) -> None:
        self.read_output, self.write_output = read_output, write_output
        self.calls: List[tuple] = []

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return {"success": True, "output": self.read_output if arguments.get("mode") == "read" else self.write_output}

    def call_is_read_only(self, name: str, arguments: Dict[str, Any]) -> bool:
        return arguments.get("mode") == "read"


def manifest() -> Dict[str, Any]:
    return json.loads((recipes.MODULE_DIR / "module.json").read_text(encoding="utf-8"))


def wire(tmp_path, monkeypatch, mode="ask_first", revit=None):
    inst = ModuleInstance(ModuleManifest(**manifest()), recipes.MODULE_DIR)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    modules = SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False))
    gate = ApprovalGate(tmp_path, mode)
    revit = revit or FakeRevit()
    workspace = WorkspaceMonitor([tmp_path])
    provider = ModuleProvider(modules, workspace)
    capabilities = {tool.name: tool for tool in provider.get_capabilities()}
    capabilities["revit_execute_python"] = SimpleNamespace(is_mutating=True)
    registry = SimpleNamespace(
        lookup_tool=lambda name: capabilities.get(name),
        lookup_tool_provider=lambda name: provider if name in capabilities and name != "revit_execute_python" else revit,
        get_provider=lambda name: SimpleNamespace(gate=gate) if name == "approval" else None,
    )
    provider.tool_registry = registry
    return SimpleNamespace(provider=provider, gate=gate, registry=registry, revit=revit, workspace=workspace, tmp=tmp_path,
                           module=inst.class_instance, store=RecipeStore(tmp_path, starter_dir=recipes.STARTER_DIR))


def run_tool(w, tool, args):
    return asyncio.run(run_gated_tool(w.registry, w.gate, tool, args))


def save(w, rid="r1", code=READ_CODE, mode="read", params=None, **kw):
    result = w.module.recipe_save(id=rid, title=kw.get("title", "T " + rid), code=code, mode=mode, params=params, description=kw.get("description", ""), workspace=w.workspace)
    assert result["ok"] is True, result
    return result


def plan_for(w, tool, arguments):
    plan = w.gate.create_plan([{"tool": tool, "arguments": arguments}], [{}])
    human_approve(w.gate, plan["plan_id"])
    return plan["plan_id"]


def sha_of(w, rid):
    return w.store.load(rid).sha256


# --------------------------------------------------------------------------- #
# Manifest and tool metadata
# --------------------------------------------------------------------------- #
def test_tool_names_and_gate_flags(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    tools = {t.name: t for t in w.provider.get_capabilities()}
    for name in (SAVE, LIST, GET, RUN, DELETE):
        assert name in tools
    assert [tools[n].is_mutating for n in (SAVE, LIST, GET)] == [False, False, False]
    assert tools[RUN].is_mutating is True and tools[DELETE].is_mutating is True and tools[DELETE].destructive is True


def _undocumented(schema: Any, path: str) -> List[str]:
    missing: List[str] = []
    if isinstance(schema, dict):
        for key, prop in (schema.get("properties") or {}).items():
            if not isinstance(prop, dict) or not prop.get("description"):
                missing.append(f"{path}.{key}")
            missing.extend(_undocumented(prop, f"{path}.{key}"))
        if isinstance(schema.get("items"), dict):
            missing.extend(_undocumented(schema["items"], f"{path}[]"))
    return missing


def test_every_parameter_is_documented():
    for cmd in manifest()["commands"]:
        assert _undocumented(cmd["input_schema"], cmd["mcp_tool"]) == [], cmd["mcp_tool"]
        assert len(cmd["title"]) > 60


# --------------------------------------------------------------------------- #
# Ids, traversal, size caps
# --------------------------------------------------------------------------- #
BAD_IDS = ["../evil", "..\\evil", "a/b", "a\\b", "A", "has space", "x" * 65, "", "con", "nul", "com1", ".", "..", "a.py", None, 5, "x\x00y", "é"]


@pytest.mark.parametrize("rid", BAD_IDS)
def test_bad_ids_are_refused_everywhere_and_write_nothing(tmp_path, monkeypatch, rid):
    w = wire(tmp_path, monkeypatch)
    with pytest.raises(RecipeError):
        validate_recipe_id(rid)
    for result in (
        w.module.recipe_save(id=rid, title="t", code=READ_CODE, workspace=w.workspace),
        w.module.recipe_get(id=rid, workspace=w.workspace),
        w.module.recipe_delete(id=rid, workspace=w.workspace),
        w.module.recipe_run(id=rid, workspace=w.workspace, tool_executor=lambda *a: None),
    ):
        assert result["ok"] is False and result["kind"] in ("invalid_id", "invalid_input"), result
    assert not list(tmp_path.rglob("*.py")) and not list(tmp_path.rglob("evil*"))
    assert w.module.call_is_read_only("recipe_run", {"id": rid}, w.workspace) is False  # malformed: stays gated


def test_the_store_never_leaves_its_folder(tmp_path):
    store = RecipeStore(tmp_path)
    for rid in ("../x", "..", "a/../b"):
        with pytest.raises(RecipeError):
            store.load(rid)
        with pytest.raises(RecipeError):
            store.save(rid, code=READ_CODE, title="t", description="", params=None, mode="read")
    assert list(tmp_path.iterdir()) == []


def test_size_caps_and_code_rules(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    big = "# " + "x" * (64 * 1024) + "\n"
    r = w.module.recipe_save(id="big", title="t", code=big, workspace=w.workspace)
    assert r["ok"] is False and r["kind"] == "code_too_large"
    edge = "#" * (64 * 1024 - 1) + "\n"
    assert w.module.recipe_save(id="edge", title="t", code=edge, workspace=w.workspace)["ok"] is True
    for code in ("", "   \n", "x = 1\x00", "from __future__ import print_function\nprint(1)\n", 5):
        assert w.module.recipe_save(id="bad", title="t", code=code, workspace=w.workspace)["ok"] is False
    assert w.module.recipe_save(id="t0", title="", code=READ_CODE, workspace=w.workspace)["ok"] is False
    assert w.module.recipe_save(id="t1", title="t", code=READ_CODE, description="d" * 1001, workspace=w.workspace)["ok"] is False
    assert not (tmp_path / "recipes" / "bad.py").exists()


# --------------------------------------------------------------------------- #
# Saving
# --------------------------------------------------------------------------- #
def test_save_writes_code_and_manifest_with_the_code_hash(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    result = save(w, "walls", READ_CODE, params=SCHEMA, description="d")
    code_file, manifest_file = tmp_path / "recipes" / "walls.py", tmp_path / "recipes" / "walls.json"
    assert code_file.read_text(encoding="utf-8") == READ_CODE
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert data["sha256"] == hashlib.sha256(READ_CODE.encode()).hexdigest() == result["recipe"]["sha256"]
    assert (data["id"], data["version"], data["mode"], data["approval"]) == ("walls", 1, "read", "per_run")
    assert [p["name"] for p in data["params"]] == ["width", "label", "count", "flag", "kind"]
    again = save(w, "walls", READ_CODE + "# more\n")
    assert again["recipe"]["version"] == 2
    assert w.revit.calls == []


def test_crlf_does_not_change_the_hash(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "crlf", READ_CODE.replace("\n", "\r\n"))
    assert sha_of(w, "crlf") == hashlib.sha256(READ_CODE.encode()).hexdigest()


def test_read_mode_is_refused_at_save_when_the_code_is_not_read_safe(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    r = w.module.recipe_save(id="w", title="t", code=WRITE_CODE, mode="read", workspace=w.workspace)
    assert r["ok"] is False and r["kind"] == "read_mode_violation" and "Transaction" in r["message"]
    assert not (tmp_path / "recipes").exists() or not list((tmp_path / "recipes").iterdir())
    assert w.module.recipe_save(id="w", title="t", code=WRITE_CODE, mode="write", workspace=w.workspace)["ok"] is True
    assert w.module.recipe_save(id="w2", title="t", code=READ_CODE, mode="maybe", workspace=w.workspace)["ok"] is False


def test_saving_is_free_even_in_look_only_and_without_a_plan(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch, mode="look_only")
    result = run_tool(w, SAVE, {"id": "a", "title": "t", "code": READ_CODE})
    assert result["ok"] is True
    assert run_tool(w, LIST, {})["counts"]["rows"] >= 1


def test_parameter_schema_is_checked_at_save(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    bad = [
        [{"name": "x", "type": "float"}],
        [{"name": "1x", "type": "string"}],
        [{"name": "x", "type": "string"}, {"name": "x", "type": "string"}],
        [{"name": "x", "type": "string", "min": 1}],
        [{"name": "x", "type": "integer", "min": 5, "max": 1}],
        [{"name": "x", "type": "integer", "default": 2.5}],
        [{"name": "x", "type": "integer", "max": 3, "default": 4}],
        [{"name": "x", "type": "string", "enum": ["a"], "default": "b"}],
        [{"name": "x", "type": "string", "colour": "red"}],
        [{"name": "x", "type": "boolean", "unit": "mm"}],
        "width",
        [{"name": f"p{i}", "type": "string"} for i in range(31)],
    ]
    for schema in bad:
        r = w.module.recipe_save(id="p", title="t", code=READ_CODE, params=schema, workspace=w.workspace)
        assert r["ok"] is False and r["kind"] == "invalid_input", schema


# --------------------------------------------------------------------------- #
# Parameter validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("supplied,needle", [
    ({}, "params.width is required"),
    ({"width": 50}, "below the minimum"),
    ({"width": 9000}, "above the maximum"),
    ({"width": "wide"}, "must be a number"),
    ({"width": True}, "must be a number"),
    ({"width": float("nan")}, "must be finite"),
    ({"width": 500, "count": 2.0}, "whole number"),
    ({"width": 500, "count": 11}, "above the maximum"),
    ({"width": 500, "flag": 1}, "true or false"),
    ({"width": 500, "label": 5}, "must be text"),
    ({"width": 500, "label": "x" * 21}, "longer than 20"),
    ({"width": 500, "kind": "roof"}, "must be one of"),
    ({"width": 500, "bogus": 1}, "unknown parameter"),
    ("width=500", "must be an object"),
])
def test_bad_params_never_reach_revit(tmp_path, monkeypatch, supplied, needle):
    w = wire(tmp_path, monkeypatch)
    save(w, "p", READ_CODE, params=SCHEMA)
    ex_calls: List[Any] = []
    result = w.module.recipe_run(id="p", params=supplied, workspace=w.workspace, tool_executor=lambda *a: ex_calls.append(a))
    assert result["ok"] is False and result["kind"] == "invalid_params" and needle in result["message"], result
    assert ex_calls == []


def test_defaults_fill_and_values_are_typed(tmp_path):
    schema = validate_param_schema(SCHEMA)
    assert validate_params(schema, {"width": 250.5}) == {"width": 250.5, "label": "A", "count": 3, "flag": False, "kind": "wall"}
    assert validate_params(schema, {"width": 250, "count": 10, "flag": True, "kind": "floor"})["count"] == 10
    with pytest.raises(RecipeError, match="larger than"):
        validate_params(validate_param_schema([{"name": f"p{i}", "type": "string", "max_length": 2000} for i in range(6)]),
                        {f"p{i}": "y" * 2000 for i in range(6)})


def test_error_messages_do_not_echo_values(tmp_path):
    schema = validate_param_schema(SCHEMA)
    for bad in ({"width": 500, "kind": "TOPSECRET-roof"}, {"width": 500, "label": "TOPSECRET" * 5}, {"width": 500, "flag": "TOPSECRET"}):
        with pytest.raises(RecipeError) as err:
            validate_params(schema, bad)
        assert "TOPSECRET" not in str(err.value)


# --------------------------------------------------------------------------- #
# Values are data: one JSON string, never spliced into the code
# --------------------------------------------------------------------------- #
NASTY = "'''; raise Exception('boom') #\n\\' \"Transaction\" eval( open( é 中 \\x41 \x00"


def _params_value(script: str) -> str:
    line = next(ln for ln in script.splitlines() if ln.startswith("PARAMS_JSON = "))
    tree = ast.parse(line.replace("u'", "'", 1))  # the u prefix is Python 2 only
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.Assign)
    return ast.literal_eval(tree.body[0].value)


def test_params_arrive_as_one_json_string_and_the_code_text_is_untouched(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    schema = [{"name": "text", "type": "string", "max_length": 200}, {"name": "n", "type": "integer", "default": 1}]
    save(w, "j", READ_CODE, params=schema)
    sha = sha_of(w, "j")
    for supplied in ({"text": "plain"}, {"text": NASTY}, {"text": "x" * 200, "n": 7}):
        w.revit.calls.clear()
        result = run_tool(w, RUN, {"id": "j", "params": supplied})
        assert result["ok"] is True, result
        script = w.revit.calls[0][1]["script"]
        assert w.revit.calls[0][1]["mode"] == "read"
        assert script.endswith("\n\n" + READ_CODE + "\n") or script.endswith(READ_CODE + "\n")
        assert script.count(READ_CODE) == 1
        compile(script.replace("PARAMS_JSON = u'", "PARAMS_JSON = '"), "recipe", "exec")  # still one valid module
        assert json.loads(_params_value(script)) == {"n": supplied.get("n", 1), "text": supplied["text"]}
        assert "boom" not in script and "Transaction" not in _params_line(script)
        assert sha_of(w, "j") == sha
        validate_read_script(script)  # words inside a value do not trip read mode


def _params_line(script: str) -> str:
    return next(ln for ln in script.splitlines() if ln.startswith("PARAMS_JSON = "))


def test_the_params_line_is_all_escapes(tmp_path):
    line = recipes.params_line(json.dumps({"a": "'; import os #"}))
    body = line[len("PARAMS_JSON = u'"):-1]
    assert all(body[i:i + 2] == "\\x" for i in range(0, len(body), 4)) and len(body) % 4 == 0
    assert "import" not in line and "'" not in body


# --------------------------------------------------------------------------- #
# Read mode is recomputed at run time
# --------------------------------------------------------------------------- #
def test_a_read_recipe_runs_without_a_plan_in_read_mode(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "r", READ_CODE)
    result = run_tool(w, RUN, {"id": "r"})
    assert result["ok"] is True and result["rows"] == [{"n": "1"}] and result["recipe"]["runs_as"] == "read"
    assert [c[1]["mode"] for c in w.revit.calls] == ["read"]
    validate_read_script(w.revit.calls[0][1]["script"])


def _flip_manifest(w, rid, **changes):
    path = tmp_path_manifest(w, rid)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


def tmp_path_manifest(w, rid):
    return w.tmp / "recipes" / f"{rid}.json"


def test_the_manifest_flag_is_not_trusted_a_read_label_on_write_code_is_refused(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "sneaky", WRITE_CODE, mode="write")
    _flip_manifest(w, "sneaky", mode="read")  # the code is unchanged, so the hash still matches
    with pytest.raises(ReadModeViolation, match="Transaction"):
        run_tool(w, RUN, {"id": "sneaky"})
    with pytest.raises(ReadModeViolation):
        run_tool(w, RUN, {"id": "sneaky", "version": 1, "sha256": sha_of(w, "sneaky")})
    assert w.revit.calls == []
    dry = run_tool(w, RUN, {"id": "sneaky", "dry_run": True})
    assert dry["ok"] is False and dry["kind"] == "read_mode_violation"


def test_code_edited_to_break_read_mode_after_a_read_check_is_refused(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "r", READ_CODE)
    # an outside edit of the code alone is a hash mismatch; with a matching manifest it is a read-mode refusal
    code_path = tmp_path / "recipes" / "r.py"
    code_path.write_text(WRITE_CODE, encoding="utf-8")
    with pytest.raises(RecipeError, match="does not match its manifest"):
        run_tool(w, RUN, {"id": "r"})
    assert w.module.recipe_run(id="r", workspace=w.workspace)["kind"] == "hash_mismatch"
    _flip_manifest(w, "r", sha256=code_sha256(WRITE_CODE))
    with pytest.raises(ReadModeViolation):
        run_tool(w, RUN, {"id": "r"})
    assert w.revit.calls == []


def test_a_write_label_on_clean_code_still_needs_a_plan_and_runs_as_read(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "cautious", READ_CODE, mode="write")
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, {"id": "cautious"})
    args = {"id": "cautious", "version": 1, "sha256": sha_of(w, "cautious"), "params": {}}
    pid = plan_for(w, RUN, args)
    result = run_tool(w, RUN, {**args, "plan_id": pid})
    assert result["ok"] is True
    assert [c[1]["mode"] for c in w.revit.calls] == ["read"]  # clean code never gets a write-mode script


def test_a_read_run_naming_other_code_is_gated(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "r", READ_CODE)
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, {"id": "r", "sha256": "0" * 64})


# --------------------------------------------------------------------------- #
# Approval binds id, version, code hash and values
# --------------------------------------------------------------------------- #
def test_a_write_recipe_needs_a_plan_and_runs_once(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write", params=SCHEMA)
    args = {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"), "params": {"width": 300}}
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, args)
    pid = plan_for(w, RUN, args)
    result = run_tool(w, RUN, {**args, "plan_id": pid})
    assert result["ok"] is True and result["changed_ids"] == [5, 6] and result["verified"] is True
    assert [c[1]["mode"] for c in w.revit.calls] == ["write"]
    assert w.gate.load_plan(pid)["actions"][0]["state"] == "executed"
    with pytest.raises(BridgeError):
        run_tool(w, RUN, {**args, "plan_id": pid})


def test_different_parameter_values_are_not_covered_by_the_plan(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write", params=SCHEMA)
    args = {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"), "params": {"width": 300}}
    pid = plan_for(w, RUN, args)
    with pytest.raises(BridgeError, match="does not approve"):
        run_tool(w, RUN, {**args, "params": {"width": 301}, "plan_id": pid})
    assert w.revit.calls == []


def test_editing_the_recipe_after_approval_invalidates_the_approval(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    args = {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"), "params": {}}
    pid = plan_for(w, RUN, args)
    save(w, "mk", WRITE_CODE.replace("recipe", "evil"), mode="write")  # edited through the tool: version 2, new hash
    result = run_tool(w, RUN, {**args, "plan_id": pid})
    assert result["ok"] is False and result["kind"] == "recipe_changed"
    assert w.revit.calls == []
    # the approved action is spent, and a call naming the new code is not what the plan approved
    new_args = {**args, "version": 2, "sha256": sha_of(w, "mk")}
    with pytest.raises(BridgeError):
        run_tool(w, RUN, {**new_args, "plan_id": pid})
    assert w.revit.calls == []


def test_editing_the_file_directly_after_approval_is_refused(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    args = {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"), "params": {}}
    pid = plan_for(w, RUN, args)
    (tmp_path / "recipes" / "mk.py").write_text(WRITE_CODE + "# tampered\n", encoding="utf-8")
    with pytest.raises(RecipeError, match="does not match its manifest"):  # refused before the approval is spent
        run_tool(w, RUN, {**args, "plan_id": pid})
    assert w.module.recipe_run(**args, workspace=w.workspace)["kind"] == "hash_mismatch"
    assert w.gate.load_plan(pid)["actions"][0].get("state") in (None, "pending")
    assert w.revit.calls == []


def test_a_write_run_without_version_and_hash_is_refused_even_with_a_plan(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    loose = {"id": "mk", "params": {}}
    pid = plan_for(w, RUN, loose)
    result = run_tool(w, RUN, {**loose, "plan_id": pid})
    assert result["ok"] is False and result["kind"] == "binding_required"
    assert w.revit.calls == []


def test_a_plan_for_a_read_flip_race_cannot_run_unapproved_write_code(tmp_path, monkeypatch):
    # The gate is asked while the recipe is clean read code; the code is then replaced by write code.
    w = wire(tmp_path, monkeypatch)
    save(w, "race", READ_CODE)
    assert w.provider.call_is_read_only(RUN, {"id": "race"}) is True
    save(w, "race", WRITE_CODE, mode="write")
    # the run that follows (gate already skipped) has no approved executor for write code without version and hash
    result = w.module.recipe_run(id="race", workspace=w.workspace, tool_executor=lambda *a: pytest.fail("sent"), approved_executor=lambda *a: pytest.fail("sent"))
    assert result["ok"] is False and result["kind"] == "binding_required"
    stale = w.module.recipe_run(id="race", sha256=hashlib.sha256(READ_CODE.encode()).hexdigest(), version=1, workspace=w.workspace,
                                tool_executor=lambda *a: pytest.fail("sent"), approved_executor=lambda *a: pytest.fail("sent"))
    assert stale["kind"] == "recipe_changed"


# --------------------------------------------------------------------------- #
# Standing approval (set only by a person, bound to id + code hash)
# --------------------------------------------------------------------------- #
def grant(w, rid):
    return w.store.grant_standing(rid, sha_of(w, rid), "tester")


def test_standing_approval_runs_without_a_plan_and_is_audited_by_hash(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write", params=[{"name": "secret", "type": "string"}])
    args = {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"), "params": {"secret": "TOPSECRET-1"}}
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, args)
    grant(w, "mk")
    assert run_tool(w, RUN, args)["ok"] is True
    assert run_tool(w, RUN, args)["ok"] is True  # standing: more than once
    assert [c[1]["mode"] for c in w.revit.calls] == ["write", "write"]
    uses = (tmp_path / "plans" / "standing" / "uses.jsonl").read_text(encoding="utf-8")
    assert uses.count("\n") == 2 and "TOPSECRET" not in uses and sha_of(w, "mk") in uses
    assert run_tool(w, GET, {"id": "mk"})["recipe"]["approval"] == "standing"


def test_saving_always_resets_the_standing_flag(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    grant(w, "mk")
    assert (tmp_path / "plans" / "standing" / "mk.json").exists()
    result = save(w, "mk", WRITE_CODE, mode="write")  # same code, saved again
    assert result["standing_reset"] is True
    assert not (tmp_path / "plans" / "standing" / "mk.json").exists()
    assert json.loads((tmp_path / "recipes" / "mk.json").read_text(encoding="utf-8"))["approval"] == "per_run"
    args = {"id": "mk", "version": 2, "sha256": sha_of(w, "mk"), "params": {}}
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, args)


def test_standing_dies_when_the_code_changes_even_behind_the_tools_back(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    old_sha = sha_of(w, "mk")
    grant(w, "mk")
    new_code = WRITE_CODE + "# changed\n"
    (tmp_path / "recipes" / "mk.py").write_text(new_code, encoding="utf-8")
    _flip_manifest(w, "mk", sha256=code_sha256(new_code))  # a consistent outside edit
    for sha in (old_sha, code_sha256(new_code)):
        with pytest.raises(BridgeError, match="plan_id"):
            run_tool(w, RUN, {"id": "mk", "version": 1, "sha256": sha, "params": {}})
    assert w.revit.calls == []


def test_standing_needs_the_matching_hash_in_the_call_and_the_right_id(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "a", WRITE_CODE, mode="write")
    save(w, "b", WRITE_CODE + "# b\n", mode="write")
    grant(w, "a")
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, {"id": "a", "version": 1, "params": {}})  # no sha256
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, {"id": "b", "version": 1, "sha256": sha_of(w, "b"), "params": {}})  # another recipe
    # an agent-written record in the recipes folder grants nothing
    (tmp_path / "recipes" / "b.standing.json").write_text(json.dumps({"id": "b", "sha256": sha_of(w, "b")}), encoding="utf-8")
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, {"id": "b", "version": 1, "sha256": sha_of(w, "b"), "params": {}})
    _flip_manifest(w, "b", approval="standing")
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, RUN, {"id": "b", "version": 1, "sha256": sha_of(w, "b"), "params": {}})


def test_standing_never_beats_look_only_and_cannot_be_granted_for_read_or_wrong_hash(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch, mode="look_only")
    save(w, "mk", WRITE_CODE, mode="write")
    save(w, "rd", READ_CODE)
    grant(w, "mk")
    with pytest.raises(BridgeError, match="Look only"):
        run_tool(w, RUN, {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"), "params": {}})
    with pytest.raises(RecipeError):
        w.store.grant_standing("mk", "0" * 64, "x")
    with pytest.raises(RecipeError, match="read recipe"):
        w.store.grant_standing("rd", sha_of(w, "rd"), "x")
    with pytest.raises(RecipeError):
        w.store.grant_standing("steps", "0" * 64, "x")


def test_no_tool_can_grant_standing(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    tools = {t.name for t in w.provider.get_capabilities()}
    assert not [t for t in tools if "standing" in t]
    for cmd in manifest()["commands"]:
        assert "approval" not in cmd["input_schema"]["properties"]
    saved = w.module.recipe_save(id="s", title="t", code=WRITE_CODE, mode="write", approval="standing", workspace=w.workspace)
    assert saved["ok"] is True and not (tmp_path / "plans" / "standing").exists()
    assert w.store.load("s").manifest["approval"] == "per_run"


def test_the_recipe_folder_cannot_be_used_to_reach_the_standing_folder(tmp_path):
    from revit_mcp_server.errors import WorkspaceViolation

    monitor = WorkspaceMonitor([tmp_path])
    with pytest.raises(WorkspaceViolation):
        monitor.assert_in_workspace(tmp_path / "plans" / "standing" / "x.json")


def test_dev_mode_and_auto_behave_like_other_write_tools(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch, mode="auto")
    save(w, "mk", WRITE_CODE, mode="write")
    args = {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"), "params": {}}
    assert run_tool(w, RUN, args)["ok"] is True  # gate off: no plan needed ...
    changed = {**args, "sha256": "f" * 64}
    assert run_tool(w, RUN, changed)["kind"] == "recipe_changed"  # ... but the hash binding still holds


# --------------------------------------------------------------------------- #
# dry_run
# --------------------------------------------------------------------------- #
def test_dry_run_runs_nothing_needs_no_plan_and_shows_the_state(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write", params=SCHEMA)
    result = run_tool(w, RUN, {"id": "mk", "dry_run": True, "params": {"width": 400}})
    assert result["ok"] is True and result["dry_run"] is True and w.revit.calls == []
    assert result["recipe"]["sha256"] == sha_of(w, "mk") and result["recipe"]["runs_as"] == "write"
    assert result["approval_state"]["needs_approval"] is True and result["approval_state"]["approval"] == "per_run"
    assert result["plan_arguments"] == {"id": "mk", "version": 1, "sha256": sha_of(w, "mk"),
                                        "params": {"width": 400, "label": "A", "count": 3, "flag": False, "kind": "wall"}}
    grant(w, "mk")
    again = run_tool(w, RUN, {"id": "mk", "dry_run": True, "params": {"width": 400}})
    assert again["approval_state"]["approval"] == "standing" and "standing" in again["summary"]


def test_dry_run_validates_and_a_non_boolean_dry_run_is_not_a_dry_run(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write", params=SCHEMA)
    assert run_tool(w, RUN, {"id": "mk", "dry_run": True, "params": {}})["kind"] == "invalid_params"
    with pytest.raises(BridgeError, match="plan_id"):  # "true" is not True: the gate applies, nothing runs
        run_tool(w, RUN, {"id": "mk", "dry_run": "true", "params": {"width": 300}})
    assert w.revit.calls == []
    direct = w.module.recipe_run(id="mk", dry_run="yes", params={"width": 300}, workspace=w.workspace)
    assert direct["ok"] is False and direct["kind"] == "invalid_input"


# --------------------------------------------------------------------------- #
# The result contract
# --------------------------------------------------------------------------- #
def test_result_contract_for_rows_plain_text_errors_and_failures(tmp_path, monkeypatch):
    for output, check in [
        (READ_OUT, lambda r: r["ok"] is True and r["summary"] == "read ok" and r["counts"]["rows"] == 1 and r["limits"]["truncated"] is False),
        ("just text\nmore", lambda r: r["ok"] is True and r["output"] == "just text\nmore" and "plain text" in r["summary"]),
        ("", lambda r: r["ok"] is False and r["kind"] == "empty_output"),
        ("ERROR\tbad_thing\tit broke", lambda r: r["ok"] is False and r["kind"] == "bad_thing"),
        ("SUMMARY\tx\nFAIL\tE1\tdefect\nCOUNT\tfail\t1", lambda r: r["ok"] is False and r["kind"] == "recipe_reported_failure" and r["fails"]),
    ]:
        w = wire(tmp_path, monkeypatch, revit=FakeRevit(read_output=output))
        save(w, "r", READ_CODE)
        result = run_tool(w, RUN, {"id": "r"})
        assert check(result), (output, result)


def test_running_and_bridge_errors_are_reported_not_raised(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "r", READ_CODE)
    result = w.module.recipe_run(id="r", workspace=w.workspace, tool_executor=lambda *a: {"status": "running", "request_id": "abc"})
    assert result["status"] == "running" and result["request_id"] == "abc"

    def boom(*a):
        raise RuntimeError("connection refused")

    assert w.module.recipe_run(id="r", workspace=w.workspace, tool_executor=boom)["kind"] == "bridge_error"
    assert w.module.recipe_run(id="r", workspace=w.workspace)["kind"] == "no_bridge"


def test_mock_mode_is_unverified(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "r", READ_CODE)
    monkeypatch.setattr(sys.modules[type(w.module).__module__], "_server_in_mock_mode", lambda: True)
    result = w.module.recipe_run(id="r", workspace=w.workspace, tool_executor=lambda *a: pytest.fail("sent"))
    assert result["verified"] is False and result["mock"] is True


# --------------------------------------------------------------------------- #
# list, get, delete, secrets
# --------------------------------------------------------------------------- #
def test_list_and_get_report_hash_mode_approval_and_problems(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mine", WRITE_CODE, mode="write", params=SCHEMA)
    save(w, "broken", READ_CODE)
    (tmp_path / "recipes" / "broken.py").write_text(READ_CODE + "# x\n", encoding="utf-8")
    listing = run_tool(w, LIST, {})
    rows = {r["id"]: r for r in listing["rows"]}
    assert {"mine", "broken", "element_count_by_category", "level_list", "warning_summary"} <= set(rows)
    assert rows["mine"]["mode"] == "write" and rows["mine"]["source"] == "workspace" and rows["mine"]["sha256"] == sha_of(w, "mine")
    assert rows["broken"]["problem"] == "hash_mismatch"
    assert rows["level_list"]["source"] == "starter"
    got = run_tool(w, GET, {"id": "mine"})
    assert got["code"] == WRITE_CODE and got["recipe"]["sha256"] == sha_of(w, "mine")
    assert got["plan_arguments"]["version"] == 1 and got["approval_state"]["needs_approval"] is True
    bad = run_tool(w, GET, {"id": "broken"})
    assert bad["ok"] is False and bad["kind"] == "hash_mismatch"
    assert run_tool(w, GET, {"id": "nope"})["kind"] == "not_found"


def test_delete_is_gated_and_removes_the_standing_record(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    grant(w, "mk")
    with pytest.raises(BridgeError, match="plan_id"):
        run_tool(w, DELETE, {"id": "mk"})
    assert (tmp_path / "recipes" / "mk.py").exists()
    pid = plan_for(w, DELETE, {"id": "mk"})
    assert run_tool(w, DELETE, {"id": "mk", "plan_id": pid})["ok"] is True
    assert not list((tmp_path / "recipes").iterdir()) and not (tmp_path / "plans" / "standing" / "mk.json").exists()
    assert w.module.recipe_delete(id="level_list", workspace=w.workspace)["kind"] == "starter_recipe"
    assert w.module.recipe_delete(id="gone", workspace=w.workspace)["kind"] == "not_found"


def test_secrets_in_parameters_are_never_logged_or_stored(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    w = wire(tmp_path, monkeypatch)
    save(w, "s", WRITE_CODE, mode="write", params=[{"name": "token", "type": "string"}])
    args = {"id": "s", "version": 1, "sha256": sha_of(w, "s"), "params": {"token": "TOPSECRET-abc123"}}
    grant(w, "s")
    run_tool(w, RUN, args)
    run_tool(w, RUN, {"id": "s", "dry_run": True, "params": {"token": "TOPSECRET-abc123"}})
    w.module.recipe_run(id="s", params={"token": 5}, workspace=w.workspace)
    assert "TOPSECRET" not in caplog.text
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "TOPSECRET" not in path.read_text(encoding="utf-8", errors="ignore"), path


# --------------------------------------------------------------------------- #
# Starter recipes (data files)
# --------------------------------------------------------------------------- #
STARTERS = ["element_count_by_category", "level_list", "warning_summary"]


@pytest.mark.parametrize("rid", STARTERS)
def test_starter_recipes_are_consistent_read_only_and_python27_safe(tmp_path, monkeypatch, rid):
    w = wire(tmp_path, monkeypatch)
    recipe = w.store.load(rid)  # raises on a hash mismatch
    assert recipe.mode == "read" and recipe.source == "starter" and recipe.version == 1
    assert recipes.read_violations(recipe) == []
    tree = ast.parse(recipe.code)
    for node in ast.walk(tree):
        assert not isinstance(node, (ast.JoinedStr, ast.AnnAssign, ast.NamedExpr))
        if isinstance(node, ast.FunctionDef):
            assert node.returns is None and all(a.annotation is None for a in node.args.args)
    compile(recipes.build_script(recipe.code, "{}").replace("PARAMS_JSON = u'", "PARAMS_JSON = '"), rid, "exec")
    run = run_tool(w, RUN, {"id": rid})
    assert run["ok"] is True and w.revit.calls[-1][1]["mode"] == "read"
    validate_read_script(w.revit.calls[-1][1]["script"])


def test_a_workspace_recipe_replaces_a_starter_with_the_same_id(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "level_list", READ_CODE, title="Mine")
    assert w.store.load("level_list").source == "workspace"
    assert w.module.recipe_delete(id="level_list", workspace=w.workspace)["ok"] is True
    assert w.store.load("level_list").source == "starter"


def test_module_files_have_no_conflict_markers():
    import re

    for path in sorted(recipes.MODULE_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".ipy"}:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                assert not re.match(r"^(<{7}|={7}|>{7})( |$)", line), f"{path.name}:{number}"


# --------------------------------------------------------------------------- #
# The command-line tool (humans only)
# --------------------------------------------------------------------------- #
def test_cli_grants_and_revokes_standing_approval(tmp_path, monkeypatch, capsys):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    sha = sha_of(w, "mk")
    assert approve_cli.main(["--workspace", str(tmp_path), "recipe-standing", "mk", "--sha256", "0" * 64, "--yes"]) == 1
    assert not (tmp_path / "plans" / "standing" / "mk.json").exists()
    assert approve_cli.main(["--workspace", str(tmp_path), "recipe-standing", "mk", "--sha256", sha, "--yes"]) == 0
    out = capsys.readouterr().out
    assert "Transaction" in out and sha in out  # the person sees the code and the hash
    record = json.loads((tmp_path / "plans" / "standing" / "mk.json").read_text(encoding="utf-8"))
    assert record["id"] == "mk" and record["sha256"] == sha and record["approved_via"] == "cli"
    assert approve_cli.main(["--workspace", str(tmp_path), "recipe-revoke", "mk"]) == 0
    assert not (tmp_path / "plans" / "standing" / "mk.json").exists()


def test_cli_refuses_without_a_terminal_and_for_bad_ids(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    save(w, "mk", WRITE_CODE, mode="write")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert approve_cli.main(["--workspace", str(tmp_path), "recipe-standing", "mk", "--sha256", sha_of(w, "mk")]) == 2
    assert approve_cli.main(["--workspace", str(tmp_path), "recipe-standing", "../x", "--sha256", "0" * 64, "--yes"]) == 1
    assert not (tmp_path / "plans" / "standing").exists() or not list((tmp_path / "plans" / "standing").iterdir())


def test_an_unknown_recipe_is_refused_with_its_own_message(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    with pytest.raises(RecipeError, match="no recipe"):
        run_tool(w, RUN, {"id": "ghost"})


def test_the_hook_keeps_the_gate_for_unknown_tools_and_commands_without_a_hook(tmp_path, monkeypatch):
    w = wire(tmp_path, monkeypatch)
    assert w.provider.call_is_read_only("revit_recipe_delete", {"id": "x"}) is False
    assert w.provider.call_is_read_only("no_such_tool", {}) is False
    assert w.module.call_is_read_only("recipe_run", "not a dict", w.workspace) is False
    assert w.module.call_is_read_only("recipe_save", {"dry_run": True}, w.workspace) is False
