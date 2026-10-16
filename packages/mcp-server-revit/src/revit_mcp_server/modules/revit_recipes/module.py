"""
revit_recipes module - a library of saved IronPython 2.7 recipes that run through the same path as revit_execute_python.

Commands (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  recipe_save    saves code + manifest under <workspace>/recipes/ (free: it only writes those two files)
  recipe_list    id, version, title, mode, approval and code hash of every recipe (the built-in starters too)
  recipe_get     one recipe with its code, params schema and the exact arguments a plan must carry
  recipe_run     runs one recipe; dry_run validates and shows the code hash and approval state, runs nothing
  recipe_delete  removes a recipe (gated: needs an approved plan)

A recipe is code plus a manifest {id, version, title, description, params, mode, approval, sha256}. The sha256 is
taken over the code with LF line endings and is recomputed from the file on every read; a manifest that disagrees with
its code is refused (hash_mismatch), never repaired. security/recipe_store.py holds the files and the standing records.

Approval (revit_recipe_run is_mutating in module.json, so the shared gate decides, see security/gating.py):
  * The approval covers the call's arguments, which must carry ``id``, ``version``, ``sha256`` (as read at run time)
    and ``params``. revit_recipe_get / dry_run print them as ``plan_arguments``. The module compares version and
    sha256 with the code it reads at run time and refuses on any difference, so editing a recipe after approval
    invalidates the approval (the approved action is consumed and the new code needs a new plan).
  * A read recipe runs with no approval ONLY when the manifest says read AND its code, recomputed now, passes
    security/read_mode.py. The manifest flag is never trusted on its own: a recipe that says read but fails the check is
    refused. ``call_is_read_only`` below is the hook the gate asks; the same decision is made again inside the run.
  * ``dry_run`` runs nothing and is never gated.
  * A standing approval (``aec-model-bridge-approve recipe-standing``) is a person's record for one recipe id and one
    code hash; the gate honours it (ApprovalGate.claim_action). Look only mode still refuses. A module cannot set it, and
    saving, editing or deleting the recipe removes it.

Parameters: the manifest declares a typed schema (name, type integer|number|string|boolean, unit, min, max, required,
default, enum, max_length). The server validates the values and sends them as ONE JSON string, ``PARAMS_JSON``, defined
by a line placed before the code; the script reads it with ``load_params()`` (scripts/_recipes.ipy). The line is a
literal made only of \\xNN escapes, so no value can end the string, add code or change the code hash, and read mode
never trips over a word inside a value.

Script layout sent to Revit: the shared prelude of the check scripts (revit/scripts/_prelude.ipy: summary(), row(), info(),
fail(), meta(), run_main(), eid(), ename(), doc_meta(), ...), scripts/_recipes.ipy, the PARAMS_JSON line, the recipe code.
A recipe prints the line protocol of check_contract.py (end with ``__output__ = run_main(main)``); plain text is
returned in ``output``. A write recipe may call ``meta("changed_ids", "1,2")``.

UNVERIFIED: nothing here has run against a live Revit. See docs/recipes-library.md.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from revit_mcp_server.check_contract import (
    PageSpec,
    ScriptOutput,
    assemble_result,
    error_result,
    mock_result,
    parse_script_output,
)
from revit_mcp_server.security.read_mode import ReadModeViolation, find_violations
from revit_mcp_server.security.recipe_store import (
    MODES,
    Recipe,
    RecipeError,
    RecipeStore,
    check_code,
    params_json,
    validate_params,
    validate_recipe_id,
)

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
STARTER_DIR = MODULE_DIR / "starter"
REVIT_PRELUDE = MODULE_DIR.parent / "revit" / "scripts" / "_prelude.ipy"
HELPERS = SCRIPT_DIR / "_recipes.ipy"
EXECUTE_TOOL = "revit_execute_python"

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

MAX_OUTPUT_CHARS = 20000
_SHA = re.compile(r"[0-9a-f]{64}")

_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "invalid_id": "Ids use a-z, 0-9, '_' and '-' (1 to 64 characters).",
    "invalid_params": "Fix the parameter values named in the message (revit_recipe_get shows the schema). Nothing was sent to Revit.",
    "not_found": "revit_recipe_list shows the recipes that exist.",
    "hash_mismatch": "The recipe files do not agree. Nothing was run. Save the recipe again with revit_recipe_save, then read its new sha256 with revit_recipe_get.",
    "recipe_changed": "The recipe is not the one that was planned. Read it again with revit_recipe_get; a changed recipe needs a new plan with the new version and sha256. Nothing was sent to Revit.",
    "binding_required": "Pass version and sha256 from revit_recipe_get (or a dry_run) so the approval covers exactly this code. Nothing was sent to Revit.",
    "read_mode_violation": "A recipe saved as read must pass read mode. Save it again with mode 'write' (it will then need an approved plan) or remove what read mode names.",
    "approval_required": "The approval gate refused the call. Nothing was sent to Revit.",
    "script_exception": "The recipe failed inside Revit. A write recipe should open its own transaction and roll it back on error; check the model before repeating it.",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id, and do not repeat a write until it has finished.",
    "no_bridge": "This tool must run inside the AEC Model Bridge server (module provider with a tool registry).",
}


# --------------------------------------------------------------------------- #
# Script building and decisions
# --------------------------------------------------------------------------- #
def params_line(json_text: str) -> str:
    """``PARAMS_JSON = u'...'`` with every character written as an escape: the value cannot leave the literal."""
    if not json_text.isascii():
        raise ValueError("parameter JSON must be ASCII")
    return "PARAMS_JSON = u'" + "".join("\\x%02x" % ord(ch) for ch in json_text) + "'"


def build_script(code: str, json_text: str) -> str:
    """Prelude + helpers + the PARAMS_JSON line + the recipe code. The code is appended unchanged."""
    parts = [
        REVIT_PRELUDE.read_text(encoding="utf-8"),
        HELPERS.read_text(encoding="utf-8"),
        params_line(json_text),
        code,
    ]
    return "\n\n".join(parts) + "\n"


def read_violations(recipe: Recipe) -> List[str]:
    """Rules of read mode that the whole script (prelude, helpers, code) breaks; recomputed on every call."""
    return find_violations(build_script(recipe.code, "{}"))


def read_run_allowed(recipe: Recipe) -> bool:
    """True when this recipe may run without approval: declared read AND its code passes read mode now.

    Raises ReadModeViolation for a recipe declared read whose code does not pass (refused outright, like a
    read-mode script sent to revit_execute_python)."""
    if recipe.mode != "read":
        return False
    hits = read_violations(recipe)
    if hits:
        raise ReadModeViolation(
            f"Recipe '{recipe.id}' is saved as read but its code breaks read mode (found: {', '.join(hits)}). "
            "Save it again with mode 'write' to run it with an approved plan."
        )
    return True


def _store(workspace: Any) -> RecipeStore:
    dirs = getattr(workspace, "allowed_directories", None)
    if not dirs:
        raise RecipeError("no_workspace", "no workspace folder is configured")
    return RecipeStore(dirs[0], starter_dir=STARTER_DIR)


def _approval_state(store: RecipeStore, recipe: Recipe) -> Dict[str, Any]:
    """What running this recipe needs right now (read mode recomputed, standing checked against the code on disk)."""
    hits = read_violations(recipe)
    refused = recipe.mode == "read" and bool(hits)
    needs = recipe.mode == "write"
    standing = needs and store.standing_valid(recipe)
    if refused:
        why = "refused: saved as read but its code breaks read mode (" + ", ".join(hits) + ")"
    elif not needs:
        why = "read recipe: its code passes read mode, so no approval is needed"
    elif standing:
        why = "standing approval set by a person for this exact code (look only mode still refuses)"
    else:
        why = "write recipe: each run needs an approved plan whose action carries plan_arguments"
    return {
        "declared_mode": recipe.mode,
        "read_mode_check": {"ok": not hits, "violations": hits},
        "approval": "standing" if standing else "per_run",
        "needs_approval": needs,
        "standing_valid": standing,
        "refused": refused,
        "reason": why,
    }


def plan_arguments(recipe: Recipe, values: Dict[str, Any]) -> Dict[str, Any]:
    """Exactly what an approved plan action for this run must carry."""
    return {"id": recipe.id, "version": recipe.version, "sha256": recipe.sha256, "params": values}


def _summary_row(recipe: Recipe, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": recipe.id,
        "version": recipe.version,
        "title": recipe.manifest["title"],
        "mode": recipe.mode,
        "approval": (state or {}).get("approval", "per_run"),
        "source": recipe.source,
        "sha256": recipe.sha256,
        "params": ", ".join(spec["name"] for spec in recipe.params),
    }


# --------------------------------------------------------------------------- #
# Seams to Revit (same shape as revit_params)
# --------------------------------------------------------------------------- #
def _server_in_mock_mode() -> bool:
    try:
        from revit_mcp_server.config import BridgeMode, config

        return config.mode == BridgeMode.mock
    except Exception:  # noqa: BLE001 - a config problem must not hide a real bridge
        return False


def _is_mock(raw: Any) -> bool:
    if isinstance(raw, dict):
        if raw.get("mock"):
            return True
        data = raw.get("data")
        return isinstance(data, dict) and bool(data.get("mock"))
    return False


def _is_running(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("status") == "running" and bool(raw.get("request_id"))


def _script_text(raw: Any) -> "tuple[Optional[str], str]":
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict) and "output" not in raw:
        raw = raw["data"]
    if not isinstance(raw, dict):
        return None, f"unexpected answer from the bridge: {type(raw).__name__}"
    if raw.get("success") is False:
        return None, str(raw.get("error") or "the script failed without a message")
    if "output" not in raw:
        return None, "the bridge answer has no 'output' field"
    return str(raw.get("output") or ""), str(raw.get("error") or "")


def _bridge_failure(tool: str, exc: Exception) -> Dict[str, Any]:
    text = str(exc)
    low = text.lower()
    if "approval" in low or "plan_id" in low:
        return error_result(tool, "approval_required", text, hint=_HINTS["approval_required"])
    if "timed out" in low or "timeout" in low:
        return error_result(tool, "timeout_running", text, hint=_HINTS["timeout_running"])
    return error_result(tool, "bridge_error", text, hint="Check that Revit is running with the AEC Model Bridge add-in and a project open (revit_health).")


def _running(tool: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tool": tool,
        "status": "running",
        "request_id": raw.get("request_id"),
        "verified": False,
        "summary": "Revit is still working on this request; the outcome is not known yet.",
        "message": raw.get("message") or "Call revit_get_result with this request_id to collect the output.",
        "hint": _HINTS["timeout_running"],
        "changed_ids": [],
    }


def _ints(text: Optional[str]) -> List[int]:
    return [int(p) for p in (text or "").split(",") if p.strip().lstrip("-").isdigit()]


def _fail(tool: str, exc: RecipeError) -> Dict[str, Any]:
    return error_result(tool, exc.kind, str(exc), hint=_HINTS.get(exc.kind, ""))


def _ok(tool: str, summary: str, extra: Dict[str, Any], page: Optional[PageSpec] = None, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    out = ScriptOutput(summary=summary, rows=rows or [])
    out.counts = {"fail": 0, "info": 0, "row": len(rows or [])}
    result = assemble_result(tool, out, page or PageSpec(), extra={"verified": True, **extra})
    return result


def _flag(value: Any, what: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise RecipeError("invalid_input", f"{what} must be true or false")
    return value


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
class RevitRecipesModule:

    # ---- gate hook ---------------------------------------------------------- #
    def call_is_read_only(self, command_id: str, arguments: Dict[str, Any], workspace: Any = None) -> bool:
        """Asked by the approval gate (ModuleProvider.call_is_read_only): True only when this call cannot change the model.

        A dry run runs nothing. A run is read-only when the recipe is declared read and its code passes read mode now,
        and the call (if it names a sha256) names the code that is on disk. Everything else keeps the gate.
        Raises ReadModeViolation for a read recipe whose code does not pass, and RecipeError for an unknown recipe or files
        that disagree (a clear refusal instead of a misleading request for a plan)."""
        if command_id != "recipe_run" or not isinstance(arguments, dict):
            return False
        if arguments.get("dry_run") is True:
            return True
        try:
            rid = validate_recipe_id(arguments.get("id"))
        except RecipeError:
            return False  # a malformed call stays gated; the run reports the real problem
        recipe = _store(workspace).load(rid)  # RecipeError: refused with its own message
        sha = arguments.get("sha256")
        if sha is not None and sha != recipe.sha256:
            return False
        return read_run_allowed(recipe)

    # ---- save --------------------------------------------------------------- #
    def recipe_save(
        self,
        id: Any = None,
        title: Any = None,
        code: Any = None,
        description: Any = "",
        params: Any = None,
        mode: Any = "read",
        workspace: Any = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_recipe_save"
        try:
            recipe_id = validate_recipe_id(id)
            if mode not in MODES:
                raise RecipeError("invalid_input", "mode must be 'read' or 'write'")
            store = _store(workspace)
            text = check_code(code)
            if mode == "read":
                hits = find_violations(build_script(text, "{}"))
                if hits:
                    raise RecipeError(
                        "read_mode_violation",
                        f"mode 'read' needs code that passes read mode (found: {', '.join(hits)}). Save it with mode 'write' to run it with an approved plan.",
                    )
            manifest = store.save(recipe_id, code=text, title=title, description=description, params=params, mode=mode)
        except RecipeError as exc:
            return _fail(tool, exc)
        reset = bool(manifest.pop("standing_reset", False))
        note = " A standing approval for the old code was removed." if reset else ""
        return _ok(
            tool,
            f"Saved recipe '{recipe_id}' version {manifest['version']} ({mode}). sha256 {manifest['sha256'][:12]}...{note}",
            {
                "recipe": {k: manifest[k] for k in ("id", "version", "title", "mode", "approval", "sha256")},
                "standing_reset": reset,
                "hint": "Saving never runs anything. " + ("A write recipe needs an approved plan for each run (revit_recipe_run). Standing approval is set only by a person with aec-model-bridge-approve." if mode == "write" else "A read recipe runs without approval."),
            },
        )

    # ---- list / get --------------------------------------------------------- #
    def recipe_list(
        self,
        limit: Any = 100,
        offset: Any = 0,
        count_only: Any = False,
        fields: Any = None,
        workspace: Any = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_recipe_list"
        try:
            store = _store(workspace)
            rows: List[Dict[str, Any]] = []
            problems: List[str] = []
            for rid in store.ids():
                try:
                    recipe = store.load(rid)
                except RecipeError as exc:
                    problems.append(f"{rid}: {exc.kind}")
                    rows.append({"id": rid, "version": "", "title": "", "mode": "", "approval": "", "source": "", "sha256": "", "params": "", "problem": exc.kind})
                    continue
                rows.append(_summary_row(recipe, {"approval": "standing" if store.standing_valid(recipe) else "per_run"}))
        except RecipeError as exc:
            return _fail(tool, exc)
        page = PageSpec.from_args(limit, offset, count_only, fields)
        text = f"{len(rows)} recipe(s)" + (f", {len(problems)} with a problem ({', '.join(problems)})" if problems else "")
        return _ok(tool, text, {"recipes_with_problems": problems}, page=page, rows=[{k: str(v) for k, v in r.items()} for r in rows])

    def recipe_get(self, id: Any = None, workspace: Any = None, **_: Any) -> Dict[str, Any]:
        tool = "revit_recipe_get"
        try:
            store = _store(workspace)
            recipe = store.load(id)
            state = _approval_state(store, recipe)
            defaults = validate_defaults(recipe)
        except RecipeError as exc:
            return _fail(tool, exc)
        return _ok(
            tool,
            f"Recipe '{recipe.id}' version {recipe.version} ({recipe.mode}), sha256 {recipe.sha256[:12]}...",
            {
                "recipe": {**{k: recipe.manifest[k] for k in ("id", "version", "title", "description", "mode", "params")}, "sha256": recipe.sha256, "source": recipe.source, "approval": state["approval"]},
                "code": recipe.code,
                "approval_state": state,
                "plan_arguments": plan_arguments(recipe, defaults) if state["needs_approval"] else None,
            },
        )

    # ---- delete ------------------------------------------------------------- #
    def recipe_delete(self, id: Any = None, workspace: Any = None, **_: Any) -> Dict[str, Any]:
        tool = "revit_recipe_delete"
        try:
            recipe_id = validate_recipe_id(id)
            _store(workspace).delete(recipe_id)
        except RecipeError as exc:
            return _fail(tool, exc)
        return _ok(tool, f"Deleted recipe '{recipe_id}' and any standing approval for it.", {"deleted": recipe_id})

    # ---- run ---------------------------------------------------------------- #
    def recipe_run(
        self,
        id: Any = None,
        params: Any = None,
        version: Any = None,
        sha256: Any = None,
        dry_run: Any = False,
        limit: Any = 100,
        offset: Any = 0,
        count_only: Any = False,
        fields: Any = None,
        workspace: Any = None,
        tool_executor: Optional[ToolExecutor] = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_recipe_run"
        try:
            dry = _flag(dry_run, "dry_run")
            store = _store(workspace)
            recipe = store.load(id)
            if sha256 is not None and (not isinstance(sha256, str) or not _SHA.fullmatch(sha256)):
                raise RecipeError("invalid_input", "sha256 must be 64 lowercase hex characters")
            if version is not None and (isinstance(version, bool) or not isinstance(version, int)):
                raise RecipeError("invalid_input", "version must be a whole number")
            if sha256 is not None and sha256 != recipe.sha256:
                raise RecipeError("recipe_changed", f"recipe '{recipe.id}' changed since sha256 {sha256[:12]}... was read (it is now {recipe.sha256[:12]}..., version {recipe.version}).")
            if version is not None and version != recipe.version:
                raise RecipeError("recipe_changed", f"recipe '{recipe.id}' is version {recipe.version}, not {version}.")
            values = validate_params(recipe.params, params)
            json_text = params_json(values)
            state = _approval_state(store, recipe)
            if state["refused"]:
                raise RecipeError("read_mode_violation", f"Recipe '{recipe.id}' is saved as read but its code breaks read mode (found: {', '.join(state['read_mode_check']['violations'])}).")
            runs_as = "read" if state["read_mode_check"]["ok"] else "write"
            page = PageSpec.from_args(limit, offset, count_only, fields)
        except RecipeError as exc:
            return _fail(tool, exc)
        info = {
            "id": recipe.id,
            "version": recipe.version,
            "sha256": recipe.sha256,
            "mode": recipe.mode,
            "runs_as": runs_as,
            "source": recipe.source,
        }
        if dry:
            return _ok(
                tool,
                f"DRY RUN, nothing was sent to Revit: recipe '{recipe.id}' version {recipe.version} would run as {runs_as}; "
                + ("no approval is needed." if not state["needs_approval"] else "a person's standing approval covers it." if state["standing_valid"] else "it needs an approved plan."),
                {
                    "dry_run": True,
                    "recipe": info,
                    "params": values,
                    "approval_state": state,
                    "plan_arguments": plan_arguments(recipe, values) if state["needs_approval"] else None,
                    "script_bytes": len(build_script(recipe.code, json_text).encode("utf-8")),
                    "hint": "Nothing was run. To run it, call revit_recipe_run again without dry_run" + (", with a plan_id for an approved plan whose action carries plan_arguments." if state["needs_approval"] and not state["standing_valid"] else "."),
                },
            )
        if runs_as == "write" and (version is None or sha256 is None):
            return error_result(tool, "binding_required", "A recipe that can change the model must be run with the version and sha256 that were approved.", hint=_HINTS["binding_required"])
        if _server_in_mock_mode():
            return mock_result(tool)
        executor = tool_executor if runs_as == "read" else approved_executor
        if executor is None:
            return error_result(
                tool,
                "no_bridge",
                "No connection to the Revit tools in this session." if runs_as == "read" else "No approved connection to Revit: a write recipe must run through the approval gate.",
                hint=_HINTS["no_bridge"],
            )
        script = build_script(recipe.code, json_text)
        started = time.perf_counter()
        try:
            raw = executor(EXECUTE_TOOL, {"script": script, "mode": runs_as})
        except Exception as exc:  # noqa: BLE001 - classified into a structured error
            return _bridge_failure(tool, exc)
        elapsed = int((time.perf_counter() - started) * 1000)
        if _is_mock(raw):
            return mock_result(tool)
        if _is_running(raw):
            return _running(tool, raw)
        text, err = _script_text(raw)
        if text is None:
            return error_result(tool, "script_error", err, hint="The add-in reported a script error before any result was produced." + (" Check the model before repeating a write." if runs_as == "write" else " Read only: the model is unchanged."))
        return self._finish(tool, info, text, elapsed, page, workspace, runs_as)

    @staticmethod
    def _finish(tool: str, info: Dict[str, Any], text: str, elapsed: int, page: PageSpec, workspace: Any, runs_as: str) -> Dict[str, Any]:
        parsed = parse_script_output(text)
        if parsed.errors:
            kind, message = parsed.errors[0]
            result = error_result(tool, kind, message, hint=_HINTS.get(kind, ""))
            result["recipe"] = info
            result["changed_ids"] = _ints(parsed.meta.get("changed_ids"))
            return result
        extra: Dict[str, Any] = {"recipe": info, "dry_run": False}
        if not parsed.summary and not parsed.counts:
            plain = text.strip()
            if not plain:
                return error_result(tool, "empty_output", "The recipe printed nothing.", hint="End the recipe with __output__ = run_main(main) and call summary() and row().")
            parsed = ScriptOutput(summary=f"Recipe returned {len(plain.splitlines())} line(s) of plain text (no SUMMARY line)")
            extra["output"] = plain[:MAX_OUTPUT_CHARS]
            extra["output_truncated"] = len(plain) > MAX_OUTPUT_CHARS
        if runs_as == "write":
            extra["changed_ids"] = _ints(parsed.meta.get("changed_ids"))
            extra["verified"] = parsed.meta.get("verified") == "1"
        result = assemble_result(tool, parsed, page, elapsed_ms=elapsed, workspace=workspace, extra=extra)
        if parsed.fails:
            result["ok"] = False
            result["kind"] = "recipe_reported_failure"
            result["message"] = parsed.fails[0]
            result["hint"] = "The recipe printed FAIL lines; they are listed in fails."
        return result


def validate_defaults(recipe: Recipe) -> Dict[str, Any]:
    """Parameter values a run would use with no params given (for the plan_arguments template of revit_recipe_get)."""
    try:
        return validate_params(recipe.params, {})
    except RecipeError:
        return {}
