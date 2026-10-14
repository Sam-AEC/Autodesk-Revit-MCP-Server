"""Output contract, script-output parser and pagination for the read-only Revit check tools.

Implements section 6 (output contract) and item 1.12 (pagination and budgets) of
``docs/upgrade-plan-hands-and-eyes.md``. It is pure Python with no Revit dependency, so
every function here is unit-testable with canned script output.

A check tool runs an embedded IronPython 2.7 script inside Revit. The script prints a
small line protocol (tab separated) instead of JSON, because the deployed IronPython
build has no ``json`` module:

    SUMMARY<TAB>text                   one line, the result in words
    FAIL<TAB>CODE<TAB>text             a defect the agent must act on
    INFO<TAB>CODE<TAB>text             a fact worth knowing, not a defect
    ROW<TAB>key=value<TAB>key=value    one record of the (pageable) result list
    META<TAB>key<TAB>value             doc_title, doc_guid, revit_version, verified, partial
    COUNT<TAB>fail|info|row<TAB>n      true totals (the script caps the lines it prints)
    ERROR<TAB>kind<TAB>message         the script could not do its job (bad input, ...)

This module turns that into ``{ok, tool, summary, fails[], info[], detail_file?, limits}``.
"""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
DETAIL_DIR_NAME = "revit_checks"

_LINE = re.compile(r"^(SUMMARY|FAIL|INFO|ERROR|ROW|META|COUNT)[\t ]+(.*)$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# --------------------------------------------------------------------------- #
# Pagination and budgets (plan item 1.12)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PageSpec:
    """Budget for one tool call: how many rows, from where, and which fields."""

    limit: int = DEFAULT_LIMIT
    offset: int = 0
    count_only: bool = False
    fields: Optional[Tuple[str, ...]] = None

    @classmethod
    def from_args(
        cls,
        limit: Any = None,
        offset: Any = None,
        count_only: Any = False,
        fields: Any = None,
    ) -> "PageSpec":
        """Clamp user input: limit 1..500 (default 50), offset >= 0, fields = non-empty names."""
        try:
            lim = int(limit) if limit is not None else DEFAULT_LIMIT
        except (TypeError, ValueError):
            lim = DEFAULT_LIMIT
        try:
            off = int(offset) if offset is not None else 0
        except (TypeError, ValueError):
            off = 0
        names: Optional[Tuple[str, ...]] = None
        if fields:
            cleaned = tuple(str(f).strip() for f in fields if str(f).strip())
            names = cleaned or None
        return cls(
            limit=max(1, min(lim, MAX_LIMIT)),
            offset=max(0, off),
            count_only=bool(count_only),
            fields=names,
        )


def paginate(items: Sequence[Any], page: PageSpec) -> Tuple[List[Any], bool]:
    """Return ``(visible slice, more_hidden)``.

    ``more_hidden`` is true when items after the window exist (so the caller should page on or read
    the detail file). ``count_only`` shows nothing and reports hidden items if there are any.
    """
    if page.count_only:
        return [], len(items) > 0
    window = list(items[page.offset : page.offset + page.limit])
    return window, page.offset + len(window) < len(items)


def project_fields(rows: Iterable[Dict[str, Any]], fields: Optional[Sequence[str]]) -> List[Dict[str, Any]]:
    """Keep only ``fields`` of each row (unknown names are ignored); ``None`` keeps everything."""
    if not fields:
        return [dict(r) for r in rows]
    return [{k: r[k] for k in fields if k in r} for r in rows]


# --------------------------------------------------------------------------- #
# Parsing the embedded script's output
# --------------------------------------------------------------------------- #
@dataclass
class ScriptOutput:
    summary: str = ""
    fails: List[str] = field(default_factory=list)
    infos: List[str] = field(default_factory=list)
    rows: List[Dict[str, str]] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    errors: List[Tuple[str, str]] = field(default_factory=list)
    ignored_lines: int = 0

    @property
    def fail_total(self) -> int:
        return max(self.counts.get("fail", 0), len(self.fails))

    @property
    def info_total(self) -> int:
        return max(self.counts.get("info", 0), len(self.infos))

    @property
    def row_total(self) -> int:
        return max(self.counts.get("row", 0), len(self.rows))


def _join_code(rest: str) -> str:
    """``CODE<TAB>text`` (or ``CODE text``) -> ``CODE: text``."""
    if "\t" in rest:
        code, _, text = rest.partition("\t")
        return f"{code.strip()}: {text.strip()}" if text.strip() else code.strip()
    return rest.strip()


def parse_script_output(text: str) -> ScriptOutput:
    """Parse the line protocol. Unknown lines are counted in ``ignored_lines`` and dropped."""
    out = ScriptOutput()
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        m = _LINE.match(line)
        if not m:
            out.ignored_lines += 1
            continue
        kind, rest = m.group(1), m.group(2)
        if kind == "SUMMARY":
            out.summary = rest.strip()
        elif kind == "FAIL":
            out.fails.append(_join_code(rest))
        elif kind == "INFO":
            out.infos.append(_join_code(rest))
        elif kind == "ERROR":
            k, _, msg = rest.partition("\t")
            out.errors.append((k.strip() or "script_error", msg.strip()))
        elif kind == "META":
            k, _, v = rest.partition("\t")
            out.meta[k.strip()] = v.strip()
        elif kind == "COUNT":
            k, _, v = rest.partition("\t")
            try:
                out.counts[k.strip()] = int(v.strip())
            except ValueError:
                out.ignored_lines += 1
        elif kind == "ROW":
            row: Dict[str, str] = {}
            for part in rest.split("\t"):
                key, sep, value = part.partition("=")
                if sep and key.strip():
                    row[key.strip()] = value
            if row:
                out.rows.append(row)
    return out


def cast_value(value: str, kind: str) -> Any:
    """Cast one row value. ``int|float|bool|intlist``; an empty numeric cell becomes ``None``; unknown kinds stay strings."""
    if kind in ("int", "float") and not value.strip():
        return None
    try:
        if kind == "int":
            return int(value)
        if kind == "float":
            return float(value)
        if kind == "bool":
            return value.strip().lower() in ("1", "true", "yes")
        if kind == "intlist":
            return [int(x) for x in value.split(",") if x.strip()]
    except ValueError:
        return value
    return value


def cast_rows(rows: Iterable[Dict[str, str]], types: Dict[str, str]) -> List[Dict[str, Any]]:
    return [{k: cast_value(v, types.get(k, "str")) for k, v in row.items()} for row in rows]


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #
def error_result(
    tool: str,
    kind: str,
    message: str,
    *,
    element_ids: Optional[List[int]] = None,
    hint: str = "",
    mock: bool = False,
) -> Dict[str, Any]:
    """``ok:false`` contract: ``kind``, ``message``, ``element_ids``, ``hint``."""
    result: Dict[str, Any] = {
        "ok": False,
        "tool": tool,
        "kind": kind,
        "message": message,
        "element_ids": list(element_ids or []),
        "hint": hint,
    }
    if mock:
        result["mock"] = True
    return result


def mock_result(tool: str) -> Dict[str, Any]:
    """Mock mode: nothing was measured, so say so at the top level (never look like a pass)."""
    return {
        "ok": True,
        "mock": True,
        "verified": False,
        "tool": tool,
        "build": None,
        "document": {"title": None, "guid": None},
        "elapsed_ms": 0,
        "summary": f"MOCK MODE: {tool} did not run against Revit. Nothing was measured. UNVERIFIED.",
        "fails": [],
        "info": ["UNVERIFIED: the server is in mock mode (MCP_REVIT_MODE=mock); this is not a model result."],
        "changed_ids": [],
        "detail_file": None,
        "limits": {"truncated": False, "partial": False},
    }


def _detail_dir(workspace: Any) -> Path:
    """``<workspace>/revit_checks``, created on demand; raises if the workspace is missing or the path escapes it."""
    if workspace is None or not getattr(workspace, "allowed_directories", None):
        raise ValueError("no workspace configured")
    base = Path(workspace.allowed_directories[0]) / DETAIL_DIR_NAME
    assert_ok = getattr(workspace, "assert_in_workspace", None)
    if callable(assert_ok):
        assert_ok(base)
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_json(workspace: Any, name: str, data: Any) -> Tuple[Optional[str], Optional[str]]:
    """Store ``data`` as ``<workspace>/revit_checks/<name>.json`` (safe names only); return ``(path, error)``."""
    if not _SAFE_NAME.match(name or ""):
        return None, "unsafe file name"
    try:
        target = _detail_dir(workspace) / f"{name}.json"
        target.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
        return str(target), None
    except Exception as exc:  # noqa: BLE001
        return None, f"could not write {name}.json: {exc}"


def load_json(workspace: Any, name: str) -> Tuple[Any, Optional[str]]:
    """Read ``<workspace>/revit_checks/<name>.json``; return ``(data, error)``."""
    if not _SAFE_NAME.match(name or ""):
        return None, "unsafe file name"
    try:
        target = _detail_dir(workspace) / f"{name}.json"
        if not target.is_file():
            return None, "not found"
        return json.loads(target.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"could not read {name}.json: {exc}"


def write_detail_file(
    workspace: Any,
    tool: str,
    header: Sequence[str],
    fails: Sequence[str],
    infos: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    *,
    stem: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Write the full lists under ``<workspace>/revit_checks/``; return ``(path, error)``.

    The path is checked with the workspace sandbox before writing (the same rule the bridge
    applies to path arguments). ``stem`` lets a caller name the file (it must be a safe name).
    """
    try:
        name = stem or f"{tool}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
        if not _SAFE_NAME.match(name):
            return None, "unsafe detail file name"
        target = _detail_dir(workspace) / f"{name}.txt"
        lines: List[str] = [f"# {h}" for h in header]
        lines += [f"FAIL\t{f}" for f in fails]
        lines += [f"INFO\t{i}" for i in infos]
        for row in rows:
            lines.append("ROW\t" + "\t".join(f"{k}={v}" for k, v in row.items()))
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(target), None
    except Exception as exc:  # noqa: BLE001 - a missing detail file must never break the check itself
        return None, f"could not write detail file: {exc}"


def assemble_result(
    tool: str,
    parsed: ScriptOutput,
    page: PageSpec,
    *,
    row_types: Optional[Dict[str, str]] = None,
    sort_key: Any = None,
    elapsed_ms: int = 0,
    workspace: Any = None,
    summary: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
    detail_stem: Optional[str] = None,
    always_detail: bool = False,
) -> Dict[str, Any]:
    """Apply budgets to parsed script output and build the section 6 contract."""
    rows_all = cast_rows(parsed.rows, row_types or {})
    if sort_key is not None:
        rows_all.sort(key=sort_key)

    fails_shown, fails_cut = paginate(parsed.fails, page)
    infos_shown, infos_cut = paginate(parsed.infos, page)
    rows_shown, rows_cut = paginate(rows_all, page)
    rows_shown = project_fields(rows_shown, page.fields)

    fail_total, info_total, row_total = parsed.fail_total, parsed.info_total, parsed.row_total
    script_capped = (
        fail_total > len(parsed.fails) or info_total > len(parsed.infos) or row_total > len(rows_all)
    )
    truncated = fails_cut or infos_cut or rows_cut or script_capped
    partial = parsed.meta.get("partial", "0") in ("1", "true", "yes")

    detail_file: Optional[str] = None
    detail_error: Optional[str] = None
    if (truncated and not page.count_only) or always_detail:
        header = [
            f"tool: {tool}",
            f"document: {parsed.meta.get('doc_title', '')} {parsed.meta.get('doc_guid', '')}".rstrip(),
            f"summary: {summary or parsed.summary}",
        ]
        detail_file, detail_error = write_detail_file(
            workspace, tool, header, parsed.fails, parsed.infos, rows_all, stem=detail_stem
        )

    limits: Dict[str, Any] = {
        "truncated": bool(truncated),
        "partial": partial,
        "limit": page.limit,
        "offset": page.offset,
        "count_only": page.count_only,
        "fields": list(page.fields) if page.fields else None,
        "fails_total": fail_total,
        "info_total": info_total,
        "rows_total": row_total,
    }
    if script_capped:
        limits["script_capped"] = True
    if detail_error:
        limits["detail_file_error"] = detail_error

    verified = parsed.meta.get("verified", "1") not in ("0", "false", "no")
    result: Dict[str, Any] = {
        "ok": True,
        "tool": tool,
        "verified": verified,
        "build": None,
        "document": {"title": parsed.meta.get("doc_title"), "guid": parsed.meta.get("doc_guid")},
        "revit_version": parsed.meta.get("revit_version"),
        "elapsed_ms": int(elapsed_ms),
        "summary": summary or parsed.summary or "(the script returned no summary)",
        "fails": fails_shown,
        "info": infos_shown,
        "rows": rows_shown,
        "counts": {"fails": fail_total, "info": info_total, "rows": row_total},
        "changed_ids": [],
        "detail_file": detail_file,
        "limits": limits,
    }
    if extra:
        result.update(extra)
    return result


def new_baseline_id() -> str:
    """Opaque id for a warnings baseline: ``wb-YYYYMMDDTHHMMSSZ-xxxx``."""
    return f"wb-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"


def is_safe_name(name: str) -> bool:
    return bool(_SAFE_NAME.match(name or ""))
