"""
naming_checker module - checks names against a convention the user provides.

Commands:
  check_names              - Validate file names, sheet numbers/names, view names and
                             level/grid names against a pattern of named fields.
  list_example_conventions - Show the bundled example convention files.

The convention is always supplied by the user: a pattern such as
``{project}-{originator}-{volume}-{level}-{type}-{role}-{number}`` plus, per field,
an allowed-value list and/or a regular expression and/or a length. Nothing here
assumes a standard, a national annex or a default code list. The bundled files
under ``conventions/`` are labelled examples with made-up placeholder codes.

Read-only and pure Python: it works the same in mock mode and on a live snapshot.
"""
from __future__ import annotations

import itertools
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONVENTIONS_DIR = Path(__file__).parent / "conventions"

KINDS = (
    "file_names",
    "sheet_numbers",
    "sheet_names",
    "view_names",
    "level_names",
    "grid_names",
)

DISCLAIMER = (
    "Results show how each name compares with the convention you provided. "
    "This tool does not check against ISO 19650 or any national annex."
)

_FIELD_RE = re.compile(r"\{([^{}]*)\}")
_NAME_RE = re.compile(r"^\w+$", re.UNICODE)
_MAX_LISTED_VALUES = 20


def _nfc(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value))


# ---------------------------------------------------------------------------
# Convention parsing
# ---------------------------------------------------------------------------

class _Convention:
    """A validated single-pattern convention."""

    def __init__(self, pattern: str, fields: Dict[str, Dict[str, Any]], tokens: List[Tuple[str, str]]):
        self.pattern = pattern
        self.fields = fields
        self.tokens = tokens
        self.field_order = [v for k, v in tokens if k == "field"]
        self.literals = [v for k, v in tokens if k == "lit"]

    def _assignments(self, name: str, use_allowed: bool, validate: bool):
        """Yield every way of splitting ``name`` over the pattern (shortest-first per field).

        With ``validate`` set, only assignments whose every field passes its own
        rules (allowed list, length, regex) are yielded.
        """
        tokens = self.tokens
        n = len(name)

        def candidates(field: str, pos: int):
            spec = self.fields[field]
            if use_allowed and spec["allowed"]:
                for alt in sorted(spec["allowed"], key=len, reverse=True):
                    end = pos + len(alt)
                    piece = name[pos:end]
                    if len(piece) == len(alt) and (
                        piece.casefold() == alt.casefold() if spec["ignore_case"] else piece == alt
                    ):
                        yield end
                return
            if spec["length"] is not None:
                if pos + spec["length"] <= n:
                    yield pos + spec["length"]
                return
            lo = pos + (spec["min_length"] or 0)
            hi = n if spec["max_length"] is None else min(n, pos + spec["max_length"])
            yield from range(lo, hi + 1)

        def walk(i: int, pos: int, acc: List[str]):
            if i == len(tokens):
                if pos == n:
                    yield list(acc)
                return
            kind, value = tokens[i]
            if kind == "lit":
                if name.startswith(value, pos):
                    yield from walk(i + 1, pos + len(value), acc)
                return
            for end in candidates(value, pos):
                piece = name[pos:end]
                if validate and _check_field(value, self.fields[value], piece) is not None:
                    continue
                acc.append(piece)
                yield from walk(i + 1, end, acc)
                acc.pop()

        for values in walk(0, 0, []):
            yield dict(zip(self.field_order, values))

    def split(self, name: str) -> Optional[Dict[str, str]]:
        """Split a name into field values, or None if it does not fit the pattern.

        Prefers an assignment in which every field satisfies its own rules (so a
        field may contain the separator when its regex/length says so). If none
        exists, returns the first structural fit so the failing fields can be named.
        """
        for use_allowed in (True, False):
            for values in itertools.islice(self._assignments(name, use_allowed, True), 1):
                return values
        for use_allowed in (True, False):
            for values in itertools.islice(self._assignments(name, use_allowed, False), 1):
                return values
        return None

    def structure_hint(self, name: str) -> str:
        seps = set(self.literals)
        if len(seps) == 1:
            sep = next(iter(seps))
            if sep and not any(sep in a for s in self.fields.values() for a in s["allowed"]):
                expected = len(self.field_order)
                found = len(name.split(sep))
                if found != expected:
                    return f" It should have {expected} parts joined by '{sep}' but has {found}."
        return ""


def _parse_field_spec(field: str, raw: Any) -> Dict[str, Any]:
    if isinstance(raw, (list, tuple)):
        raw = {"allowed": list(raw)}
    if not isinstance(raw, dict):
        raise ValueError(f"Field '{field}' must be an object (or a list of allowed values).")
    unknown = set(raw) - {
        "allowed", "regex", "length", "min_length", "max_length", "ignore_case", "description",
    }
    if unknown:
        raise ValueError(f"Field '{field}' has unknown settings: {', '.join(sorted(unknown))}.")
    allowed = raw.get("allowed") or []
    if not isinstance(allowed, (list, tuple)) or not all(isinstance(a, (str, int)) for a in allowed):
        raise ValueError(f"Field '{field}': 'allowed' must be a list of values.")
    if "allowed" in raw and not allowed:
        raise ValueError(f"Field '{field}': 'allowed' is empty, so nothing could ever pass.")
    spec: Dict[str, Any] = {
        "allowed": [_nfc(a) for a in allowed],
        "ignore_case": bool(raw.get("ignore_case", False)),
        "regex": None,
        "length": None,
        "min_length": None,
        "max_length": None,
    }
    for key in ("length", "min_length", "max_length"):
        if raw.get(key) is not None:
            val = raw[key]
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                raise ValueError(f"Field '{field}': '{key}' must be a whole number of 0 or more.")
            spec[key] = val
    if raw.get("regex") is not None:
        try:
            spec["regex"] = re.compile(str(raw["regex"]))
        except re.error as exc:
            raise ValueError(f"Field '{field}': the regex is not valid ({exc}).") from exc
    return spec


def _parse_convention(conv: Any, label: str = "convention") -> _Convention:
    if not isinstance(conv, dict):
        raise ValueError(f"The {label} must be an object with a 'pattern' and 'fields'.")
    pattern = conv.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError(f"The {label} needs a 'pattern', for example '{{project}}-{{number}}'.")
    pattern = _nfc(pattern)

    # Brace balance: every '{' / '}' must belong to a {field}.
    leftover = _FIELD_RE.sub("", pattern)
    if "{" in leftover or "}" in leftover:
        raise ValueError(
            f"The pattern '{pattern}' has an unmatched or empty brace. Write each field as {{name}}."
        )

    tokens: List[Tuple[str, str]] = []
    pos = 0
    for m in _FIELD_RE.finditer(pattern):
        if m.start() > pos:
            tokens.append(("lit", pattern[pos:m.start()]))
        name = m.group(1).strip()
        if not name or not _NAME_RE.match(name):
            raise ValueError(
                f"The pattern '{pattern}' has an invalid field name '{m.group(1)}'. "
                "Use letters, digits or underscores."
            )
        tokens.append(("field", name))
        pos = m.end()
    if pos < len(pattern):
        tokens.append(("lit", pattern[pos:]))

    names = [v for k, v in tokens if k == "field"]
    if not names:
        raise ValueError(f"The pattern '{pattern}' has no {{field}} in it.")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"The pattern uses the same field twice: {', '.join(dupes)}.")

    fields_raw = conv.get("fields")
    if not isinstance(fields_raw, dict):
        raise ValueError(f"The {label} needs a 'fields' object with one entry per field in the pattern.")
    missing = [n for n in names if n not in fields_raw]
    if missing:
        raise ValueError(
            f"No rules given for field(s) used in the pattern: {', '.join(missing)}. "
            "Add an entry for each (an empty {} means any non-empty value)."
        )
    extra = sorted(set(fields_raw) - set(names))
    if extra:
        raise ValueError(f"Rules given for field(s) not in the pattern: {', '.join(extra)}.")

    specs = {n: _parse_field_spec(n, fields_raw[n]) for n in names}

    # Two fields next to each other with no separator cannot be split reliably
    # unless the first has a fixed length or a fixed allowed list.
    for i in range(len(tokens) - 1):
        if tokens[i][0] == "field" and tokens[i + 1][0] == "field":
            first = specs[tokens[i][1]]
            if first["length"] is None and not first["allowed"]:
                raise ValueError(
                    f"Fields '{tokens[i][1]}' and '{tokens[i + 1][1]}' are next to each other with no "
                    f"separator. Put a separator between them, or give '{tokens[i][1]}' a fixed "
                    "'length' or an 'allowed' list."
                )
    return _Convention(pattern, specs, tokens)


def _parse_conventions(raw: Any) -> Dict[Optional[str], _Convention]:
    """Return {kind: convention}; key None means 'applies to every kind'."""
    if not isinstance(raw, dict):
        raise ValueError("The convention must be an object.")
    if "by_kind" in raw:
        by_kind = raw["by_kind"]
        if not isinstance(by_kind, dict) or not by_kind:
            raise ValueError("'by_kind' must list at least one kind with its own pattern and fields.")
        out: Dict[Optional[str], _Convention] = {}
        for kind, conv in by_kind.items():
            if kind not in KINDS:
                raise ValueError(f"Unknown kind '{kind}' in 'by_kind'. Use one of: {', '.join(KINDS)}.")
            out[kind] = _parse_convention(conv, f"convention for {kind}")
        return out
    return {None: _parse_convention(raw)}


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

def _check_field(field: str, spec: Dict[str, Any], value: str) -> Optional[str]:
    """Return a plain-language reason the value fails, or None if it passes."""
    if value == "":
        return "is empty"
    if spec["allowed"]:
        if spec["ignore_case"]:
            ok = value.casefold() in {a.casefold() for a in spec["allowed"]}
        else:
            ok = value in spec["allowed"]
        if not ok:
            shown = spec["allowed"][:_MAX_LISTED_VALUES]
            more = len(spec["allowed"]) - len(shown)
            listed = ", ".join(shown) + (f" (and {more} more)" if more > 0 else "")
            return f"'{value}' is not one of the allowed values: {listed}"
    if spec["length"] is not None and len(value) != spec["length"]:
        return f"'{value}' should be exactly {spec['length']} characters but is {len(value)}"
    if spec["min_length"] is not None and len(value) < spec["min_length"]:
        return f"'{value}' is shorter than the minimum of {spec['min_length']} characters"
    if spec["max_length"] is not None and len(value) > spec["max_length"]:
        return f"'{value}' is longer than the maximum of {spec['max_length']} characters"
    if spec["regex"] is not None and not spec["regex"].fullmatch(value):
        return f"'{value}' does not match the required format /{spec['regex'].pattern}/"
    return None


def _check_name(conv: _Convention, raw_name: Any) -> Dict[str, Any]:
    name = _nfc(raw_name) if raw_name is not None else ""
    failures: List[Dict[str, str]] = []
    values: Optional[Dict[str, str]] = None

    if name != name.strip():
        failures.append({
            "field": "(whole name)",
            "value": name,
            "reason": "has spaces at the start or end",
        })
    elif name == "":
        failures.append({"field": "(whole name)", "value": "", "reason": "is empty"})
    else:
        values = conv.split(name)
        if values is None:
            failures.append({
                "field": "(whole name)",
                "value": name,
                "reason": f"does not follow the pattern {conv.pattern}." + conv.structure_hint(name),
            })
        else:
            for field in conv.field_order:
                reason = _check_field(field, conv.fields[field], values[field])
                if reason:
                    failures.append({"field": field, "value": values[field], "reason": reason})
    return {
        "name": name,
        "passed": not failures,
        "fields": values,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Snapshot extraction
# ---------------------------------------------------------------------------

# Parameter labels are stored by Revit in the user's language. Known aliases
# (best effort, not exhaustive); anything else is reported, never guessed.
SHEET_NUMBER_KEYS = ("Sheet Number", "Number", "Blattnummer", "Numéro de feuille", "Numero foglio", "Número de plano")
SHEET_NAME_KEYS = ("Sheet Name", "Name", "Blattname", "Nom de la feuille", "Nome foglio", "Nombre de plano")
VIEW_NAME_KEYS = ("View Name", "Name", "Ansichtsname", "Nom de la vue", "Nome vista", "Nombre de vista")
GENERIC_NAME_KEYS = ("Name", "Name (Bezeichnung)", "Nom", "Nome", "Nombre")

VIEWS_INCOMPLETE_REASON = (
    "Not enough data for view names: this snapshot may not contain every view in the model "
    "(the Revit add-in currently saves only drafting views, not floor plans, sections, "
    "elevations, 3D views or schedules). Views that were found are checked below, but a "
    "pass here does NOT mean all views follow the convention."
)
VIEWS_MISSING_REASON = (
    "Not enough data for view names: this snapshot contains no views at all (the Revit "
    "add-in needs to save every view type), so view names could not be checked."
)


def _param_text(el: Dict[str, Any], *keys: str) -> Optional[str]:
    params = el.get("params") or {}
    for key in keys:
        p = params.get(key)
        if isinstance(p, dict) and p.get("v") not in (None, ""):
            return str(p["v"])
    explicit = el.get("name")
    if explicit not in (None, "") and "Name" in keys:
        return str(explicit)
    return None


def _names_from_snapshot(data: Dict[str, Any]) -> Tuple[Dict[str, List[str]], Dict[str, Any]]:
    out: Dict[str, List[str]] = {k: [] for k in KINDS}
    # missing: elements with no name under any known label; typed: used type_name instead.
    info: Dict[str, Any] = {"missing": {}, "typed": {}, "elements": {}}

    def note(kind: str, key: str) -> None:
        info[key][kind] = info[key].get(kind, 0) + 1

    def pick(el, kind, keys, allow_type_name=True):
        info["elements"][kind] = info["elements"].get(kind, 0) + 1
        v = _param_text(el, *keys)
        if v is None and allow_type_name and el.get("type_name"):
            note(kind, "typed")
            return str(el["type_name"])
        if v is None:
            note(kind, "missing")
        return v

    source = data.get("source") or {}
    title = source.get("doc_title")
    if title:
        out["file_names"].append(str(title))
    for el in data.get("elements", []):
        cat = el.get("category")
        if cat == "OST_Sheets":
            number = pick(el, "sheet_numbers", SHEET_NUMBER_KEYS, allow_type_name=False)
            name = pick(el, "sheet_names", SHEET_NAME_KEYS)
            if number:
                out["sheet_numbers"].append(number)
            if name:
                out["sheet_names"].append(name)
        elif cat == "OST_Views":
            name = pick(el, "view_names", VIEW_NAME_KEYS)
            if name:
                out["view_names"].append(name)
        elif cat == "OST_Levels":
            name = pick(el, "level_names", GENERIC_NAME_KEYS)
            if name:
                out["level_names"].append(name)
        elif cat == "OST_Grids":
            name = pick(el, "grid_names", GENERIC_NAME_KEYS)
            if name:
                out["grid_names"].append(name)
    info["views_complete"] = source.get("views_complete") is True
    return out, info


def _lookup_notes(info: Dict[str, Any], selected: List[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for kind in selected:
        miss = info["missing"].get(kind, 0)
        typed = info["typed"].get(kind, 0)
        label = kind.replace("_", " ")
        if miss:
            rows.append({"kind": kind, "reason": (
                f"Not enough data: {miss} of {info['elements'].get(kind, 0)} {label} could not be read "
                "because none of the known parameter labels (English, German, French, Italian, Spanish) "
                "matched this snapshot, so they were not checked. The Revit add-in needs to save the "
                "element name in a language-independent field.")})
        if typed:
            rows.append({"kind": kind, "reason": (
                f"{typed} {label} had no readable name label, so the type name was checked instead "
                "(it may not be the name you see in Revit).")})
    return rows


# ---------------------------------------------------------------------------
# Module class
# ---------------------------------------------------------------------------

class NamingCheckerModule:

    def check_names(
        self,
        convention: Optional[Dict[str, Any]] = None,
        convention_file: str = "",
        names: Optional[Dict[str, Any]] = None,
        snapshot_id: str = "",
        kinds: Optional[List[str]] = None,
        workspace: Any = None,
        **_,
    ) -> Dict[str, Any]:
        if convention is None or convention == {}:
            if not convention_file:
                raise ValueError(
                    "Provide your naming convention in 'convention' (or name a file in 'convention_file'). "
                    "This tool has no built-in convention."
                )
            convention = self._load_convention_file(convention_file, workspace)
        conventions = _parse_conventions(convention)

        if kinds is not None:
            bad = [k for k in kinds if k not in KINDS]
            if bad:
                raise ValueError(f"Unknown kind(s): {', '.join(bad)}. Use any of: {', '.join(KINDS)}.")

        to_check: Dict[str, List[Any]] = {k: [] for k in KINDS}
        if names is not None:
            if not isinstance(names, dict):
                raise ValueError("'names' must be an object such as {\"file_names\": [\"...\"]}.")
            for kind, values in names.items():
                if kind not in KINDS:
                    raise ValueError(f"Unknown kind '{kind}' in 'names'. Use any of: {', '.join(KINDS)}.")
                if isinstance(values, str):
                    values = [values]
                if not isinstance(values, (list, tuple)):
                    raise ValueError(f"'names.{kind}' must be a list of names.")
                to_check[kind].extend(values)
        selected = [k for k in KINDS if (kinds is None or k in kinds)]
        incomplete: List[Dict[str, str]] = []
        views_incomplete = False
        if snapshot_id:
            snap = self._load_snapshot(snapshot_id, workspace)
            snap_names, info = _names_from_snapshot(snap)
            for kind, values in snap_names.items():
                to_check[kind].extend(values)
            incomplete.extend(_lookup_notes(info, selected))
            if "view_names" in selected and not info["views_complete"]:
                views_incomplete = True
                incomplete.append({
                    "kind": "view_names",
                    "reason": VIEWS_INCOMPLETE_REASON if snap_names["view_names"] else VIEWS_MISSING_REASON,
                })
        results: List[Dict[str, Any]] = []
        by_kind: Dict[str, Dict[str, int]] = {}
        skipped: Dict[str, int] = {}
        for kind in selected:
            items = to_check[kind]
            if not items:
                continue
            conv = conventions.get(kind) or conventions.get(None)
            if conv is None:
                skipped[kind] = len(items)
                continue
            counts = {"checked": 0, "passed": 0, "failed": 0}
            for raw in items:
                res = _check_name(conv, raw)
                res["kind"] = kind
                results.append(res)
                counts["checked"] += 1
                counts["passed" if res["passed"] else "failed"] += 1
            by_kind[kind] = counts

        failed_fields: Dict[str, int] = {}
        for res in results:
            for f in res["failures"]:
                failed_fields[f["field"]] = failed_fields.get(f["field"], 0) + 1

        checked = len(results)
        passed = sum(1 for r in results if r["passed"])
        notes: List[str] = []
        if checked == 0 and not skipped:
            notes.append("No names were supplied, so nothing was checked.")
        for kind, n in skipped.items():
            notes.append(f"{n} {kind.replace('_', ' ')} not checked: your convention has no pattern for them.")

        for row in incomplete:
            notes.append(row["reason"])
        if views_incomplete and "view_names" in by_kind:
            by_kind["view_names"]["complete"] = False

        return {
            "summary": {
                "checked": checked,
                "passed": passed,
                "failed": checked - passed,
                "not_checked": sum(skipped.values()),
            },
            "complete": not incomplete,
            "not_enough_data": incomplete,
            "by_kind": by_kind,
            "failures_by_field": failed_fields,
            "results": results,
            "notes": notes,
            "disclaimer": DISCLAIMER,
        }

    def list_example_conventions(self, **_) -> Dict[str, Any]:
        examples = []
        for path in sorted(CONVENTIONS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            examples.append({
                "name": path.stem,
                "label": data.get("label", ""),
                "covers": sorted((data.get("by_kind") or {}).keys()),
            })
        return {
            "examples": examples,
            "note": "These are examples with placeholder codes only. Write your own convention for real checks.",
        }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _load_convention_file(self, ref: str, workspace: Any) -> Dict[str, Any]:
        example = CONVENTIONS_DIR / f"{ref}.json"
        if re.fullmatch(r"[A-Za-z0-9_\-]+", ref) and example.is_file():
            path = example
        else:
            if workspace is None:
                raise ValueError(f"Convention file '{ref}' not found. Use list_example_conventions for names.")
            path = Path(ref)
            roots = [Path(d) for d in workspace.allowed_directories]
            if not path.is_absolute():
                path = roots[0] / path
            resolved = path.resolve()
            if not any(resolved == r.resolve() or r.resolve() in resolved.parents for r in roots):
                raise ValueError("The convention file must be inside the workspace.")
            path = resolved
            if not path.is_file():
                raise ValueError(f"Convention file '{ref}' not found in the workspace.")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"Convention file '{ref}' is not valid JSON: {exc}") from exc

    def _load_snapshot(self, snapshot_id: str, workspace: Any) -> Dict[str, Any]:
        if workspace is None:
            raise ValueError("A workspace is required to read a snapshot.")
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", snapshot_id):
            raise ValueError(f"Snapshot '{snapshot_id}' not found.")
        snap_path = workspace.allowed_directories[0] / "snapshots" / f"{snapshot_id}.json"
        if not snap_path.exists():
            raise ValueError(f"Snapshot '{snapshot_id}' not found.")
        with open(snap_path, encoding="utf-8") as f:
            return json.load(f)
