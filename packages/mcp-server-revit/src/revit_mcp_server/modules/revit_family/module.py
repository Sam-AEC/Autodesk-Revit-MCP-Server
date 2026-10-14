"""
revit_family module - make a loadable Revit family from DATA instead of a hand-written script.

Command (the MCP tool name is the ``mcp_tool`` of the command in module.json):
  make_family   WRITE   one to five families from specs (name, category, box w/d/h, ports with a pipe, duct or electrical
                        connector): built from a family template, saved as .rfa inside the workspace, loaded into the
                        project, then checked with the existing read-only revit_probe_family

The spec format is the one of docs/recipes/villa2/m1_specs.json and the build is a port of
docs/recipes/villa2/m1_mep_families.py: category set on the family, a body box (extrusion), one small port cube per port
with a ConnectorElement on the cube face named by ``dir``, one family type, SaveAs, LoadFamily. Two differences from the
recipe: the family comes from a real family template (Application.NewFamilyDocument) instead of the project's own "Pole"
family, and the load reads the saved file (Document.LoadFamily with a path).

How it works: like the revit_docs module, the command builds an IronPython 2.7 script from the revit module's
``_prelude.ipy`` plus this module's ``scripts/_write_prelude.ipy`` and ``scripts/make_family.ipy``, injects the checked
arguments as an ``ARGS`` literal and runs it in Revit. The seams to Revit are ``run_write_script`` (the build) and
``run_read_script`` (the probe afterwards), both through the executor the approval gate hands the command.

Guards, all before anything is sent to Revit:
  * every spec field is checked; unknown keys, bad numbers, bad names and duplicate names are refused (``invalid_input``);
  * category guard: the port kinds must fit the category (``category_mismatch``). mech: pipe/duct/elec with at least one
    pipe or duct; plumb: pipe/elec with at least one pipe; air: duct/elec with at least one duct; elec_eq, elec_fx and
    light: elec only;
  * ``output_dir`` and ``template_path`` must lie inside the workspace sandbox (``path_outside_workspace``).

Template: an explicit ``template_path`` is used as given. Otherwise the script searches Application.FamilyTemplatePath for
a template whose name fits the category and falls back to the generic model template, saying so. It never guesses a path:
when nothing is found the call fails with ``template_not_found`` and a message that says where it looked. Every family row
and the result carry the template that was used.

Safety of the write command:
  * it is ``is_mutating`` in module.json, so the approval gate demands an approved plan_id before it starts;
  * the project changes only when a family is loaded, inside one TransactionGroup with one Transaction per family. on_error
    'abort' (default) rolls the whole group back on the first failure and deletes the .rfa files this call wrote; 'skip'
    keeps the families that worked. Each family document is closed again (try/finally) on every path, saved or not;
  * an existing .rfa file or an existing project family of the same name is refused unless ``replace`` is true (then the
    file is overwritten and the family is loaded over; an overwritten file is not restored by a rollback);
  * Revit warnings are dismissed and listed (INFO REVIT_WARNING_DISMISSED);
  * after the load the existing read-only ``revit_probe_family`` (modules/revit, through its own seam) runs for each loaded
    family. Its verdict (nested instances, category, connector list) is merged into ``post_check``; the result is never
    ``ok: true`` when a script check or a probe check failed;
  * ``dry_run``: each family document is built and checked as normal, then closed unsaved. No folder or .rfa file is
    written, nothing is loaded, the project group is rolled back, the probe does not run, and the rows name the file a
    real run would write. It is approval-gated like a real run. UNVERIFIED in a live Revit like the rest.

Everything that needs a running Revit is UNVERIFIED here: the scripts are syntax-checked and exercised against stubs of
the Revit API in the tests (tests/test_revit_family.py, tests/test_revit_family_scripts.py), not against Revit. In
particular unverified: Application.NewFamilyDocument on the installed templates, the template file-name search, face
references and ConnectorElement creation on the port cubes, the connector size and flow parameters, SaveAs and
Document.LoadFamily(path) inside a transaction, rolling back a group that loaded a family, and the real probe verdict.
"""
from __future__ import annotations

import importlib.util
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from revit_mcp_server.check_contract import (
    DRY_RUN_HINT,
    PageSpec,
    ScriptOutput,
    assemble_result,
    error_result,
    mock_result,
    parse_script_output,
    write_run_fields,
)

MODULE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = MODULE_DIR / "scripts"
# The line protocol and the shared read-only helpers are those of the revit module.
REVIT_MODULE_DIR = MODULE_DIR.parent / "revit"
REVIT_PRELUDE = REVIT_MODULE_DIR / "scripts" / "_prelude.ipy"
WRITE_PRELUDE = "_write_prelude.ipy"
EXECUTE_TOOL = "revit_execute_python"
MAX_SPECS = 5
MAX_PORTS = 40

ToolExecutor = Callable[[str, Dict[str, Any]], Any]

# Category key -> (Revit name for messages, port kinds allowed, kinds of which at least one is required)
CATEGORIES: Dict[str, Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = {
    "mech": ("Mechanical Equipment", ("pipe", "duct", "elec"), ("pipe", "duct")),
    "plumb": ("Plumbing Fixtures", ("pipe", "elec"), ("pipe",)),
    "air": ("Air Terminals", ("duct", "elec"), ("duct",)),
    "elec_eq": ("Electrical Equipment", ("elec",), ()),
    "elec_fx": ("Electrical Fixtures", ("elec",), ()),
    "light": ("Lighting Fixtures", ("elec",), ()),
}
SYSTEMS = {
    "pipe": ("cold", "hot", "san", "vent", "hsup", "hret"),
    "duct": ("supply", "return", "exhaust", "outdoor"),
    "elec": ("power", "data"),
}
DIRS = ("+x", "-x", "+y", "-y", "+z", "-z")
FLOWS = ("in", "out", "both")
KIND_ALIASES = {"electrical": "elec"}
DOMAIN_OF_KIND = {"pipe": "Piping", "duct": "Hvac", "elec": "Electrical"}
SPEC_KEYS = {"name", "category", "w", "d", "h", "ports"}
PORT_KEYS = {"pos", "dir", "kind", "system", "dia_mm", "flow", "label"}

_BAD_NAME_CHARS = set("\\/:*?\"<>|{}[];`~")
_LABEL = re.compile(r"^[ -~]{1,80}$")

_HINTS = {
    "invalid_input": "Fix the argument named in the message and call again. Nothing was sent to Revit.",
    "category_mismatch": "Use a category whose connectors fit the ports (mech: pipe/duct, plumb: pipe, air: duct, elec_eq/elec_fx/light: elec), or fix the port kinds. Nothing was sent to Revit.",
    "path_outside_workspace": "Use a path inside the allowed workspace directories (see revit_get_context for the workspace folder).",
    "template_not_found": "Pass template_path (a .rft file copied into the workspace) or install the Revit family templates and set their folder in Revit Options > File Locations. No path is guessed.",
    "file_exists": "Pass replace=true to overwrite the file, or choose another output_dir or name.",
    "family_exists": "Pass replace=true to load over the family in the project, or choose another name.",
    "wrong_document": "Open the project that should receive the families and call again.",
    "rolled_back": "Nothing was changed in the project and the .rfa files written by this call were removed. Fix the cause named in fails and call again, or pass on_error='skip' to keep what worked.",
    "partial_failure": "The families that worked were kept (see changed_ids); the failed ones are in fails. Fix the cause and call again for those names only.",
    "post_check_failed": "The families were loaded but a check afterwards failed (see post_check). Inspect them with revit_probe_family, then fix the spec and call again with replace=true.",
    "script_exception": "The embedded script failed inside Revit; any open transaction group was rolled back, so the project should be unchanged (verify with revit_warnings_delta).",
    "timeout_running": "Revit may still be running the script. Call revit_get_result with the request_id, and do not repeat the write until it has finished.",
    "dry_run_not_honoured": "A dry run reported committed changes. Check the project and the output folder before doing anything else.",
}


class CategoryMismatch(ValueError):
    """The category does not fit the connector kinds of the ports."""


class _OutsideWorkspace(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Script building and the seams to Revit
# --------------------------------------------------------------------------- #
def py2_literal(value: Any) -> str:
    """Python 2.7 source for a JSON-like value; strings become ``u'...'`` with ``\\uXXXX`` escapes (IronPython 2.7 needs the u)."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("numbers must be finite")
        return repr(value)
    if isinstance(value, str):
        out: List[str] = []
        for ch in value:
            code = ord(ch)
            if ch == "\\":
                out.append("\\\\")
            elif ch == "'":
                out.append("\\'")
            elif 0x20 <= code < 0x7F:
                out.append(ch)
            elif code > 0xFFFF:
                code -= 0x10000
                out.append("\\u%04x\\u%04x" % (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
            else:
                out.append("\\u%04x" % code)
        return "u'" + "".join(out) + "'"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(py2_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{py2_literal(str(k))}: {py2_literal(v)}" for k, v in value.items()) + "}"
    raise ValueError(f"cannot embed a {type(value).__name__} in a script")


def build_script(script_name: str, args: Dict[str, Any], *, write: bool = True) -> str:
    """Revit prelude + write prelude + ``ARGS`` literal + the tool script."""
    parts = [REVIT_PRELUDE.read_text(encoding="utf-8")]
    if write:
        parts.append((SCRIPT_DIR / WRITE_PRELUDE).read_text(encoding="utf-8"))
    parts.append(f"ARGS = {py2_literal(args)}")
    parts.append((SCRIPT_DIR / script_name).read_text(encoding="utf-8"))
    return "\n\n".join(parts) + "\n"


def run_write_script(script: str, approved_executor: ToolExecutor) -> Any:
    """Send the build script to Revit (mode 'write') with the executor the approval gate handed this command."""
    return approved_executor(EXECUTE_TOOL, {"script": script, "mode": "write"})


def run_read_script(script: str, executor: ToolExecutor) -> Any:
    """Send a read-only script to Revit (mode 'read'). The probe uses its own seam; this one is kept for symmetry and tests."""
    return executor(EXECUTE_TOOL, {"script": script, "mode": "read"})


_REVIT_MODULE: List[Any] = []


def revit_module() -> Any:
    """The ``revit`` module (modules/revit/module.py) with the existing probe_family.

    The module registry registers module.py files under ``revit_mcp_server.modules.<id>`` and so replaces the package of
    that name, which makes a normal ``import ...modules.revit.module`` unreliable. Load the file under a private name
    once instead; it only uses absolute imports and keeps no state that matters here.
    """
    if not _REVIT_MODULE:
        path = REVIT_MODULE_DIR / "module.py"
        spec = importlib.util.spec_from_file_location("_revit_family_revit_module", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _REVIT_MODULE.append(mod)
    return _REVIT_MODULE[0]


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


def _script_text(raw: Any) -> Tuple[Optional[str], str]:
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
        return error_result(tool, "approval_required", text, hint="The approval gate refused the call. Nothing was sent to Revit.")
    if "timed out" in low or "timeout" in low:
        return error_result(tool, "timeout_running", text, hint=_HINTS["timeout_running"])
    return error_result(tool, "bridge_error", text, hint="Check that Revit is running with the AEC Model Bridge add-in and a project open (revit_health).")


def _ints(text: Optional[str]) -> List[int]:
    return [int(p) for p in (text or "").split(",") if p.strip().lstrip("-").isdigit()]


def _mock(tool: str) -> Dict[str, Any]:
    result = mock_result(tool)
    result["post_check"] = {"ok": None, "checked": 0, "failed": 0, "checks": []}
    return result


def _running(tool: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Revit is still busy with the script; nothing was lost and the outcome is not known yet."""
    return {
        "tool": tool,
        "status": "running",
        "request_id": raw.get("request_id"),
        "verified": False,
        "summary": "Revit is still working on this request; the outcome is not known yet.",
        "message": raw.get("message") or "Call revit_get_result with this request_id to collect the output.",
        "hint": _HINTS["timeout_running"],
        "changed_ids": [],
        "post_check": None,
    }


def _run_build(
    tool: str, args: Dict[str, Any], approved_executor: Optional[ToolExecutor]
) -> Tuple[Optional[ScriptOutput], int, Optional[Dict[str, Any]]]:
    """Run the build script. Returns ``(parsed, elapsed_ms, early_result)``; ``early_result`` is an error, mock or running contract."""
    if _server_in_mock_mode():
        return None, 0, _mock(tool)
    if approved_executor is None:
        return None, 0, error_result(
            tool,
            "no_bridge",
            "No approved connection to Revit: a write command must run through the approval gate.",
            hint="This tool must run inside the AEC Model Bridge server (module provider with a tool registry).",
        )
    script = build_script("make_family.ipy", args, write=True)
    started = time.perf_counter()
    try:
        raw = run_write_script(script, approved_executor)
    except Exception as exc:  # noqa: BLE001 - classified into a structured error
        return None, 0, _bridge_failure(tool, exc)
    elapsed = int((time.perf_counter() - started) * 1000)
    if _is_mock(raw):
        return None, elapsed, _mock(tool)
    if _is_running(raw):
        return None, elapsed, _running(tool, raw)
    text, err = _script_text(raw)
    if text is None:
        return None, elapsed, error_result(tool, "script_error", err, hint="The add-in reported a script error before any result was produced. Check the project before repeating the write.")
    parsed = parse_script_output(text)
    if parsed.errors:
        kind, message = parsed.errors[0]
        result = error_result(tool, kind, message, hint=_HINTS.get(kind, ""))
        result["changed_ids"] = _ints(parsed.meta.get("changed_ids"))
        result["outcome"] = parsed.meta.get("outcome")
        result["post_check"] = None
        return None, elapsed, result
    if not parsed.summary and not parsed.counts:
        return None, elapsed, error_result(tool, "unparsable_output", "The script printed no summary and no counts (ignored %d lines)." % parsed.ignored_lines, hint="The add-in may run an older or different IronPython engine; call revit_get_context and report the build.")
    return parsed, elapsed, None


# --------------------------------------------------------------------------- #
# Spec validation (nothing reaches Revit unless all of this passes)
# --------------------------------------------------------------------------- #
def _num(value: Any, what: str, *, positive: bool = False, limit: float = 50.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{what} must be a finite number")
    number = float(value)
    if positive and number <= 0:
        raise ValueError(f"{what} must be greater than 0")
    if abs(number) > limit:
        raise ValueError(f"{what} is out of range (at most {limit:g} in absolute value)")
    return number


def _family_name(value: Any, what: str) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(f"{what} is required")
    if len(text) > 100:
        raise ValueError(f"{what} is longer than 100 characters")
    if any(ord(c) < 32 for c in text):
        raise ValueError(f"{what} contains control characters")
    bad = sorted(c for c in set(text) if c in _BAD_NAME_CHARS)
    if bad:
        raise ValueError(f"{what} '{text}' contains characters that are not allowed in a file name: {' '.join(bad)}")
    if text.endswith("."):
        raise ValueError(f"{what} must not end with a dot")
    return text


def _port(value: Any, where: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    unknown = sorted(set(value) - PORT_KEYS)
    if unknown:
        raise ValueError(f"{where} has unknown keys: {', '.join(unknown)} (allowed: {', '.join(sorted(PORT_KEYS))})")
    kind = KIND_ALIASES.get(value.get("kind"), value.get("kind"))
    if kind not in SYSTEMS:
        raise ValueError(f"{where}.kind must be one of pipe, duct, elec (electrical is accepted too), got {value.get('kind')!r}")
    pos = value.get("pos")
    if not isinstance(pos, (list, tuple)) or len(pos) != 3:
        raise ValueError(f"{where}.pos must be a list of 3 numbers [x, y, z] in metres")
    direction = value.get("dir")
    if direction not in DIRS:
        raise ValueError(f"{where}.dir must be one of {', '.join(DIRS)}, got {direction!r}")
    system = value.get("system")
    if system in (None, "") and kind == "elec":
        system = "power"
    if system not in SYSTEMS[kind]:
        raise ValueError(f"{where}.system must be one of {', '.join(SYSTEMS[kind])} for a {kind} port, got {system!r}")
    port: Dict[str, Any] = {
        "pos": [_num(c, f"{where}.pos") for c in pos],
        "dir": direction,
        "kind": kind,
        "system": system,
    }
    if kind == "elec":
        if value.get("dia_mm") is not None:
            raise ValueError(f"{where}.dia_mm does not apply to an electrical port")
        if value.get("flow") is not None:
            raise ValueError(f"{where}.flow does not apply to an electrical port")
    else:
        if value.get("dia_mm") is None:
            raise ValueError(f"{where}.dia_mm is required for a {kind} port (millimetres)")
        port["dia_mm"] = _num(value["dia_mm"], f"{where}.dia_mm", positive=True, limit=5000.0)
        if value.get("flow") not in (None, ""):
            if value["flow"] not in FLOWS:
                raise ValueError(f"{where}.flow must be one of {', '.join(FLOWS)}, got {value['flow']!r}")
            port["flow"] = value["flow"]
    label = value.get("label")
    if label not in (None, ""):
        if not isinstance(label, str) or not _LABEL.match(label):
            raise ValueError(f"{where}.label must be 1-80 printable ASCII characters")
        port["label"] = label
    return port


def validate_spec(value: Any, index: int) -> Dict[str, Any]:
    """Check one spec and return it normalised. Raises ValueError (bad data) or CategoryMismatch (category vs port kinds)."""
    where = f"specs[{index}]"
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object with name, category, w, d, h and ports")
    unknown = sorted(set(value) - SPEC_KEYS)
    if unknown:
        raise ValueError(f"{where} has unknown keys: {', '.join(unknown)} (allowed: {', '.join(sorted(SPEC_KEYS))})")
    name = _family_name(value.get("name"), f"{where}.name")
    where = f"specs[{index}] '{name}'"
    category = value.get("category")
    if category not in CATEGORIES:
        raise ValueError(f"{where}: category must be one of {', '.join(CATEGORIES)}, got {category!r}")
    ports_in = value.get("ports", [])
    if not isinstance(ports_in, list):
        raise ValueError(f"{where}.ports must be a list")
    if len(ports_in) > MAX_PORTS:
        raise ValueError(f"{where}.ports has {len(ports_in)} entries; at most {MAX_PORTS}")
    ports = [_port(p, f"{where}.ports[{i}]") for i, p in enumerate(ports_in)]
    seen: Dict[Tuple[Any, ...], int] = {}
    for i, p in enumerate(ports):
        key = (tuple(p["pos"]), p["dir"])
        if key in seen:
            raise ValueError(f"{where}.ports[{i}] repeats ports[{seen[key]}] (same pos and dir)")
        seen[key] = i
    label, allowed, required = CATEGORIES[category]
    kinds = sorted({p["kind"] for p in ports})
    wrong = [k for k in kinds if k not in allowed]
    if wrong:
        raise CategoryMismatch(
            f"{where}: category '{category}' ({label}) takes {'/'.join(allowed)} connectors, but the ports include {'/'.join(wrong)}; "
            "use a category that fits or change the port kinds"
        )
    if required and not any(k in required for k in kinds):
        raise CategoryMismatch(
            f"{where}: category '{category}' ({label}) needs at least one {' or '.join(required)} port, the ports are "
            f"{('/'.join(kinds)) if kinds else 'empty'}; a {label.lower()} family without one cannot be routed to"
        )
    return {
        "name": name,
        "category": category,
        "w": _num(value.get("w"), f"{where}.w", positive=True),
        "d": _num(value.get("d"), f"{where}.d", positive=True),
        "h": _num(value.get("h"), f"{where}.h", positive=True),
        "ports": ports,
    }


def _in_workspace(workspace: Any, candidate: Path) -> Path:
    """Resolve a path and require it inside the workspace sandbox (the same rule the bridge applies to path arguments)."""
    if workspace is None or not getattr(workspace, "assert_in_workspace", None):
        raise _OutsideWorkspace("no workspace is configured, so no path can be validated")
    try:
        return workspace.assert_in_workspace(Path(candidate))
    except Exception as exc:  # noqa: BLE001 - WorkspaceViolation or an OS error while resolving
        raise _OutsideWorkspace(str(exc)) from exc


def _flag(value: Any, what: str) -> bool:
    """A strict boolean (None means false): the string 'false' must never turn into a real write or a dry run."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(f"{what} must be true or false")
    return value


def _bad_input(tool: str, exc: Exception) -> Dict[str, Any]:
    return error_result(tool, "invalid_input", str(exc), hint=_HINTS["invalid_input"])


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #
ITEM_TYPES = {"id": "int", "ports": "int", "types": "int", "bytes": "int"}


def _finish_write(
    tool: str,
    parsed: ScriptOutput,
    elapsed: int,
    workspace: Any,
    *,
    extra_checks: Optional[List[Dict[str, Any]]] = None,
    extra_fails: Optional[List[str]] = None,
    extra_infos: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    outcome = parsed.meta.get("outcome", "ok")
    changed = _ints(parsed.meta.get("changed_ids"))
    failed_ids = _ints(parsed.meta.get("failed_ids"))
    posts = [r for r in parsed.rows if r.get("row_type") == "post"]
    items = [{k: v for k, v in r.items() if k != "row_type"} for r in parsed.rows if r.get("row_type") == "item"]
    checks = [{"check": r.get("check"), "ok": r.get("ok") == "1", "detail": r.get("detail", "")} for r in posts]
    checks.extend(extra_checks or [])
    checks.sort(key=lambda c: c["ok"])  # failures first
    failed_checks = sum(1 for c in checks if not c["ok"])
    post_check: Dict[str, Any] = {"ok": failed_checks == 0, "checked": len(checks), "failed": failed_checks, "checks": checks[:80]}

    fails = list(parsed.fails) + list(extra_fails or [])
    infos = list(parsed.infos) + list(extra_infos or [])
    synthetic = ScriptOutput(
        summary=parsed.summary,
        fails=fails,
        infos=infos,
        rows=items,
        meta=dict(parsed.meta),
        counts={"fail": parsed.fail_total + len(extra_fails or []), "info": parsed.counts.get("info", len(parsed.infos)) + len(extra_infos or []), "row": len(items)},
    )
    templates = sorted({str(i.get("template")) for i in items if i.get("template")})
    fields: Dict[str, Any] = {
        "changed_ids": changed if outcome in ("ok", "partial_failure", "post_check_failed") else [],
        "post_check": post_check,
        "outcome": outcome,
        "on_error": parsed.meta.get("on_error"),
        "warnings_dismissed": int(parsed.meta.get("warnings_dismissed", "0") or 0),
        "templates": templates,
        "template": templates[0] if len(templates) == 1 else None,
    }
    if extra:
        fields.update(extra)
    run_fields, violation = write_run_fields(parsed, outcome, items, dry_run=dry_run)
    fields.update(run_fields)
    if violation:
        fails.insert(0, violation)
        outcome = "dry_run_not_honoured"
        fields["outcome"] = outcome
    ok = outcome == "ok" and post_check["ok"] and not fails and parsed.fail_total == 0
    summary = parsed.summary
    if not ok:
        first = fails[0] if fails else outcome
        summary = f"FAILED ({outcome if outcome != 'ok' else 'post_check_failed'}): {first}"
        if outcome == "rolled_back":
            summary += " The whole call was rolled back; the project is unchanged."
    if dry_run:
        summary = "DRY RUN, nothing was changed or written: " + (summary or "")
    result = assemble_result(
        tool,
        synthetic,
        PageSpec(),
        row_types=ITEM_TYPES,
        elapsed_ms=elapsed,
        workspace=workspace,
        summary=summary,
        extra=fields,
    )
    if not ok:
        result["ok"] = False
        result["kind"] = outcome if outcome != "ok" else "post_check_failed"
        result["message"] = fails[0] if fails else f"outcome: {outcome}"
        result["element_ids"] = failed_ids
        result["hint"] = _HINTS.get(result["kind"], "")
    if dry_run and not violation:
        result["hint"] = (DRY_RUN_HINT + " " + result.get("hint", "")).strip()
    return result


# --------------------------------------------------------------------------- #
# The probe after the load (the existing read-only revit_probe_family)
# --------------------------------------------------------------------------- #
def _check(name: str, ok: bool, detail: str) -> Dict[str, Any]:
    return {"check": name, "ok": bool(ok), "detail": detail}


def probe_verdict(spec: Dict[str, Any], family_id: Optional[int], probe: Dict[str, Any], script_category_ok: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Turn the answer of revit_probe_family into a verdict and post checks for one family."""
    name = spec["name"]
    label, _allowed, _req = CATEGORIES[spec["category"]]
    checks: List[Dict[str, Any]] = []
    verdict: Dict[str, Any] = {"family": name, "id": family_id, "verdict": "UNVERIFIED", "nested_instances": None, "category": None,
                               "category_expected": label, "category_ok": None, "connectors": [], "fails": []}
    if not isinstance(probe, dict) or probe.get("ok") is False or probe.get("status") == "running":
        why = "the probe did not run"
        if isinstance(probe, dict):
            why = str(probe.get("message") or probe.get("summary") or why)
        checks.append(_check(f"probe_ran:{name}", False, f"revit_probe_family could not check the loaded family: {why}"))
        return verdict, checks
    if probe.get("mock"):
        checks.append(_check(f"probe_ran:{name}", False, "revit_probe_family answered in mock mode; nothing was measured"))
        return verdict, checks
    rows = probe.get("rows") or []
    fails = [str(f) for f in (probe.get("fails") or [])]
    limits = probe.get("limits") or {}
    complete = not limits.get("truncated") and not limits.get("partial")
    checks.append(_check(f"probe_ran:{name}", complete, "revit_probe_family finished" if complete else "revit_probe_family output was truncated or partial; the verdict cannot be trusted"))
    fam_rows = [r for r in rows if r.get("kind") == "family"]
    nested = [r for r in rows if r.get("kind") == "nested"]
    connectors = [r for r in rows if r.get("kind") == "connector" and r.get("scope") == "family"]
    probe_cat = str(fam_rows[0].get("category")) if fam_rows else None
    # The probe reports the category by its (possibly localised) display name. A name that is the English name of the expected
    # category passes; the English name of another category fails; any other name (a localised Revit) falls back to the
    # script's own check by category id.
    others = {v[0].lower() for k, v in CATEGORIES.items() if v[0].lower() != label.lower()} | {"generic models"}
    named = (probe_cat or "").lower()
    cat_ok = bool(fam_rows) and (named == label.lower() or (named not in others and bool(script_category_ok)))
    want: Dict[str, int] = {}
    for p in spec["ports"]:
        want[DOMAIN_OF_KIND[p["kind"]]] = want.get(DOMAIN_OF_KIND[p["kind"]], 0) + 1
    got: Dict[str, int] = {}
    for c in connectors:
        for dom in DOMAIN_OF_KIND.values():
            if dom in str(c.get("domain", "")):
                got[dom] = got.get(dom, 0) + 1
    checks.append(_check(f"probe_nested_instances:{name}", not nested, f"{len(nested)} nested instances in the family document"))
    checks.append(_check(f"probe_category:{name}", cat_ok, f"probe reports '{probe_cat}', expected '{label}' (the script also checked the category by id)"))
    checks.append(_check(f"probe_connectors:{name}", len(connectors) == len(spec["ports"]) and got == want, f"{len(connectors)} connectors in the family document ({got}), the spec has {len(spec['ports'])} ports ({want})"))
    checks.append(_check(f"probe_fails:{name}", not fails, "no FAIL line" if not fails else "; ".join(fails[:3])))
    verdict.update(
        nested_instances=len(nested),
        category=probe_cat,
        category_ok=cat_ok,
        connectors=[{k: c.get(k) for k in ("domain", "system", "size", "flow", "dir", "origin")} for c in connectors],
        fails=fails,
    )
    verdict["verdict"] = "PASS" if all(c["ok"] for c in checks) and probe.get("verified", True) is not False else ("FAIL" if any(not c["ok"] for c in checks) else "UNVERIFIED")
    return verdict, checks


# --------------------------------------------------------------------------- #
# The module
# --------------------------------------------------------------------------- #
class RevitFamilyModule:

    def make_family(
        self,
        specs: Any = None,
        output_dir: Any = None,
        template_path: Any = None,
        replace: Any = False,
        on_error: Any = None,
        dry_run: Any = False,
        workspace: Any = None,
        approved_executor: Optional[ToolExecutor] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        tool = "revit_make_family"
        try:
            if not isinstance(specs, list) or not specs:
                raise ValueError("specs must be a list of 1 to %d family specs" % MAX_SPECS)
            if len(specs) > MAX_SPECS:
                raise ValueError(f"at most {MAX_SPECS} families per call (the bridge waits 30 s); send the rest in another call")
            clean = [validate_spec(s, i) for i, s in enumerate(specs)]
            names = [s["name"].lower() for s in clean]
            for i, n in enumerate(names):
                if n in names[:i]:
                    raise ValueError(f"specs[{i}] repeats the name '{clean[i]['name']}' (family and file names are not case sensitive)")
            if on_error not in (None, "", "abort", "skip"):
                raise ValueError(f"on_error must be one of abort, skip, got {on_error!r}")
            if not isinstance(output_dir, str) or not output_dir.strip():
                raise ValueError("output_dir is required: a folder inside the workspace for the .rfa files")
            target = _in_workspace(workspace, Path(output_dir))
            template = ""
            if template_path not in (None, ""):
                if not isinstance(template_path, str) or Path(template_path).suffix.lower() != ".rft":
                    raise ValueError("template_path must be the path of a .rft family template file")
                template = str(_in_workspace(workspace, Path(template_path)))
            dry = _flag(dry_run, "dry_run")
        except _OutsideWorkspace as exc:
            return error_result(tool, "path_outside_workspace", str(exc), hint=_HINTS["path_outside_workspace"])
        except CategoryMismatch as exc:
            return error_result(tool, "category_mismatch", str(exc), hint=_HINTS["category_mismatch"])
        except (TypeError, ValueError) as exc:
            return _bad_input(tool, exc)

        args = {
            "specs": clean,
            "output_dir": str(target),
            "template_path": template,
            "replace": bool(replace),
            "on_error": on_error or "abort",
            "dry_run": dry,
        }
        parsed, elapsed, early = _run_build(tool, args, approved_executor)
        if early is not None or parsed is None:
            return early or {}

        extra_checks: List[Dict[str, Any]] = []
        extra_fails: List[str] = []
        extra_infos: List[str] = []
        verdicts: List[Dict[str, Any]] = []
        outcome = parsed.meta.get("outcome", "ok")
        if dry:
            extra_infos.append("PROBE_SKIPPED: dry run, no family was saved or loaded, so revit_probe_family did not run")
        elif outcome in ("ok", "partial_failure", "post_check_failed"):
            loaded = {r.get("name"): r for r in parsed.rows if r.get("row_type") == "item" and r.get("kind") == "family"}
            script_cat_ok = {
                str(r.get("check", "")).split(":", 1)[1]: r.get("ok") == "1"
                for r in parsed.rows
                if r.get("row_type") == "post" and str(r.get("check", "")).startswith("category:")
            }
            for spec in clean:
                row = loaded.get(spec["name"])
                if row is None:
                    continue
                try:
                    family_id: Optional[int] = int(row.get("id"))
                except (TypeError, ValueError):
                    family_id = None
                probe = self._probe(family_id, spec["name"], approved_executor, workspace)
                verdict, checks = probe_verdict(spec, family_id, probe, script_cat_ok.get(spec["name"], False))
                verdicts.append(verdict)
                extra_checks.extend(checks)
                for c in checks:
                    if not c["ok"]:
                        extra_fails.append("POST_CHECK_FAILED: %s: %s" % (c["check"], c["detail"]))
                for note in (probe.get("info") or []) if isinstance(probe, dict) else []:
                    extra_infos.append("PROBE: " + str(note))
        result = _finish_write(
            tool, parsed, elapsed, workspace,
            extra_checks=extra_checks, extra_fails=extra_fails, extra_infos=extra_infos,
            extra={"probe": verdicts, "output_dir": str(target)},
            dry_run=dry,
        )
        if isinstance(result.get("post_check"), dict):
            result["post_check"]["probe"] = verdicts
        if result.get("ok") and any(v["verdict"] != "PASS" for v in verdicts):
            result["verified"] = False
        return result

    def _probe(self, family_id: Optional[int], name: str, executor: Optional[ToolExecutor], workspace: Any) -> Dict[str, Any]:
        """Run the existing read-only revit_probe_family on one loaded family (by id, deep, nested instances not allowed)."""
        try:
            probe = revit_module().RevitModule().probe_family(
                ids=[family_id] if family_id is not None else None,
                name="" if family_id is not None else name,
                deep=True,
                allow_nested=False,
                expect_connectors=True,
                max_families=1,
                limit=500,
                workspace=workspace,
                tool_executor=executor,
            )
        except Exception as exc:  # noqa: BLE001 - a probe failure is a failed check, not a crash
            return {"ok": False, "message": f"{exc.__class__.__name__}: {exc}"}
        return probe if isinstance(probe, dict) else {"ok": False, "message": "unexpected probe answer"}
