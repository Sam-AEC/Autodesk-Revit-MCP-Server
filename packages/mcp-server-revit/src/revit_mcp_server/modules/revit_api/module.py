"""Revit API lookup: answer "does this member exist and what is its signature" from the documentation XML.

Agents writing scripts for ``revit_execute_python`` sometimes invent API members. This module reads the
documentation XML that ships next to the Revit DLLs (RevitAPI.xml, RevitAPIUI.xml) and answers from it, without
Revit running. Pure Python, read-only, no network.

* Sources, in order: ``doc_xml_path`` (must be inside the workspace sandbox), an installed Revit 2024-2027,
  the NuGet cache (nice3point.revit.api.revitapi). Nothing found gives an UNVERIFIED result, never a guess.
* The parsed index is built on the first call and cached as gzip JSON in the user cache dir (not the repo),
  keyed by file path, size and modification time. Only the last used index stays in memory.
* The XML holds no return types and no inheritance, so results say so where it matters.
"""
from __future__ import annotations

import difflib
import gzip
import hashlib
import json
import os
import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOOL = "revit_api_lookup"
INDEX_VERSION = 2
YEARS = (2027, 2026, 2025, 2024)
MODES = ("auto", "type", "member", "signature", "namespace")
SUMMARY_CHARS = 160
MAX_LIMIT = 200
KIND_LABEL = {"M": "method", "P": "property", "F": "field", "E": "event"}

_LOCK = threading.Lock()
_LOADED: Dict[str, Any] = {}  # {"key": cache key, "index": index}; one index at a time keeps memory modest


# --------------------------------------------------------------------------- #
# Finding the documentation
# --------------------------------------------------------------------------- #
def _program_files() -> List[Path]:
    roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), "C:/Program Files"]
    out: List[Path] = []
    for r in roots:
        if r and Path(r) not in out:
            out.append(Path(r))
    return out


def _nuget_roots() -> List[Path]:
    roots = []
    if os.environ.get("NUGET_PACKAGES"):
        roots.append(Path(os.environ["NUGET_PACKAGES"]))
    roots.append(Path.home() / ".nuget" / "packages")
    return roots


def _installed(year: int) -> List[Path]:
    for root in _program_files():
        folder = root / "Autodesk" / f"Revit {year}"
        api = folder / "RevitAPI.xml"
        if api.is_file():
            ui = folder / "RevitAPIUI.xml"
            return [api] + ([ui] if ui.is_file() else [])
    return []


def _nuget(year: Optional[int]) -> Tuple[Optional[str], List[Path]]:
    """Newest nice3point package (or the one for ``year``) that carries RevitAPI.xml, plus the matching UI XML."""
    for root in _nuget_roots():
        pkg = root / "nice3point.revit.api.revitapi"
        if not pkg.is_dir():
            continue
        versions = []
        for v in pkg.iterdir():
            m = re.match(r"(20\d\d)\.", v.name)
            if m and (year is None or int(m.group(1)) == year):
                versions.append((tuple(int(x) for x in re.findall(r"\d+", v.name)), m.group(1), v))
        for _, yr, v in sorted(versions, reverse=True):
            api = sorted(v.glob("*/**/RevitAPI.xml"))
            if not api:
                continue
            files = [api[0]]
            ui_pkg = root / "nice3point.revit.api.revitapiui" / v.name
            ui = sorted(ui_pkg.glob("*/**/RevitAPIUI.xml")) if ui_pkg.is_dir() else []
            return yr, files + ui[:1]
    return None, []


def _year_from_path(p: Path) -> Optional[str]:
    m = re.search(r"(20[2-3]\d)", str(p))
    return m.group(1) if m else None


def find_docs(year: Optional[int] = None) -> Tuple[Optional[str], List[Path], str]:
    """(year, files, origin) for the newest installed docs, or for ``year`` only when given."""
    for y in ([year] if year else list(YEARS)):
        files = _installed(y)
        if files:
            return str(y), files, "installed Revit"
    yr, files = _nuget(year)
    if files:
        return yr, files, "NuGet cache"
    return None, [], ""


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _short_type(t: str) -> str:
    t = t.replace("{", "<").replace("}", ">")
    out = "out/ref " if t.endswith("@") else ""
    t = t.rstrip("@")
    t = re.sub(r"``(\d+)", lambda m: "T" if m.group(1) == "0" else "T" + m.group(1), t)
    t = re.sub(r"`(\d+)", "", t)
    t = re.sub(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+", lambda m: m.group(0).rsplit(".", 1)[1], t)
    return out + t


def _split_params(text: str) -> List[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    bits: List[str] = []

    def walk(e: ET.Element) -> None:
        if e.text:
            bits.append(e.text)
        for child in e:
            if child.tag in ("see", "seealso", "paramref", "typeparamref") and not (child.text or "").strip():
                ref = child.get("cref") or child.get("name") or child.get("langword") or ""
                bits.append(ref.split(":", 1)[-1].rsplit(".", 1)[-1] if ref else "")
            walk(child)
            if child.tail:
                bits.append(child.tail)

    walk(el)
    s = re.sub(r"\s+", " ", "".join(bits)).strip()
    return s if len(s) <= SUMMARY_CHARS else s[: SUMMARY_CHARS - 3].rstrip() + "..."


def _check_safe(path: Path) -> None:
    with open(path, "rb") as fh:
        head = fh.read(4096)
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError(f"{path.name} declares a DOCTYPE or entities; refusing to parse it")
    if b"<doc" not in head:
        raise ValueError(f"{path.name} is not a .NET documentation XML file (no <doc> root)")


def parse_files(files: List[Path]) -> Dict[str, Any]:
    """Index: types {full name: [kind, summary]}, members {type: [[kind, name, params, summary, param names]]}."""
    types: Dict[str, List[str]] = {}
    members: Dict[str, List[list]] = {}
    for path in files:
        _check_safe(path)
        for _, el in ET.iterparse(str(path), events=("end",)):
            if el.tag != "member":
                continue
            name = el.get("name") or ""
            if len(name) > 2 and name[1] == ":":
                kind, body = name[0], name[2:]
                summary = _text(el.find("summary"))
                if kind == "T":
                    types.setdefault(body, ["type", ""])[1] = summary
                elif kind in KIND_LABEL:
                    params = None
                    head = body
                    if "(" in body:
                        head = body[: body.index("(")]
                        params = body[body.index("(") + 1 : body.rindex(")")]
                    if "." in head:
                        owner, member = head.rsplit(".", 1)
                        pnames = [p.get("name") or "" for p in el.findall("param")]
                        members.setdefault(owner, []).append([kind, member, params, summary, pnames])
                        types.setdefault(owner, ["type", ""])
            el.clear()
    for owner, rows in members.items():
        if rows and all(r[0] == "F" for r in rows):
            types[owner][0] = "enum"
    return {"version": INDEX_VERSION, "types": types, "members": members}


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "aec-model-bridge" / "revit_api"


def _cache_key(files: List[Path]) -> str:
    h = hashlib.sha1(f"v{INDEX_VERSION}".encode())
    for f in files:
        st = f.stat()
        h.update(f"|{f.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()[:20]


def load_index(files: List[Path]) -> Dict[str, Any]:
    key = _cache_key(files)
    with _LOCK:
        if _LOADED.get("key") == key:
            return _LOADED["index"]
        target = cache_dir() / f"index-{key}.json.gz"
        index = None
        try:
            with gzip.open(target, "rt", encoding="utf-8") as fh:
                index = json.load(fh)
            if index.get("version") != INDEX_VERSION:
                index = None
        except (OSError, ValueError):
            index = None
        if index is None:
            index = parse_files(files)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                    json.dump(index, fh, separators=(",", ":"))
                os.replace(tmp, target)
            except OSError:
                pass  # a cache we cannot write only costs the next call a re-parse
        _LOADED.clear()
        _LOADED.update(key=key, index=index)
        return index


# --------------------------------------------------------------------------- #
# Formatting and search
# --------------------------------------------------------------------------- #
def _short(full: str) -> str:
    return full.rsplit(".", 1)[-1]


def _namespace(index: Dict[str, Any], full: str) -> str:
    ns = full
    while "." in ns:
        ns = ns.rsplit(".", 1)[0]
        if ns not in index["types"]:
            return ns
    return ""


def _sig(owner: str, row: list) -> str:
    kind, name, params, _, pnames = row
    shown = _short(owner) if name == "#ctor" else name
    label = f"{_short(owner)}.{shown}" if name != "#ctor" else f"new {shown}"
    if kind != "M" and params is None:
        return label
    plist = _split_params(params) if params else []
    args = []
    for i, p in enumerate(plist):
        nm = pnames[i] if i < len(pnames) and pnames[i] else ""
        args.append(f"{_short_type(p)} {nm}".strip())
    if kind == "P":
        return f"{label}[{', '.join(args)}]"
    return f"{label}({', '.join(args)})"


def _line(owner: str, row: list, extra: str = "") -> str:
    tag = "value" if row[0] == "F" else KIND_LABEL[row[0]]
    text = f"{tag:8} {_sig(owner, row)}{extra}"
    return f"{text}  - {row[3]}" if row[3] else text


def _resolve_types(index: Dict[str, Any], q: str) -> List[str]:
    types = index["types"]
    if q in types:
        return [q]
    low = q.lower()
    exact = [t for t in types if t.lower() == low]
    if exact:
        return exact
    tail = "." + low
    return sorted(t for t in types if t.lower().endswith(tail))


def _all_member_names(index: Dict[str, Any]) -> List[str]:
    names = set()
    for rows in index["members"].values():
        for r in rows:
            if r[1] != "#ctor":
                names.add(r[1])
    return sorted(names)


def _suggest(index: Dict[str, Any], name: str, owners: Optional[List[str]] = None) -> List[str]:
    """Nearest real names: first among the given types' members, then across the whole API."""
    out: List[str] = []
    low = name.lower()
    if owners:
        local = {}
        for o in owners:
            for r in index["members"].get(o, []):
                local.setdefault(r[1], f"{_short(o)}.{r[1]}")
        for n in difflib.get_close_matches(name, list(local), n=5, cutoff=0.5):
            out.append(local[n])
        for n, label in local.items():
            if low and (low in n.lower() or n.lower() in low) and label not in out:
                out.append(label)
    pool = _all_member_names(index)
    lower = {n.lower(): n for n in pool}
    hits = difflib.get_close_matches(low, list(lower), n=8, cutoff=0.6)
    for h in hits:
        real = lower[h]
        holders = [o for o, rows in index["members"].items() if any(r[1] == real for r in rows)]
        label = f"{_short(holders[0])}.{real}" + (f" (+{len(holders) - 1} types)" if len(holders) > 1 else "")
        if not any(s.split(" ")[0] == label.split(" ")[0] for s in out):
            out.append(label)
    return out[:8]


# --------------------------------------------------------------------------- #
# The tool
# --------------------------------------------------------------------------- #
def _result(status: str, query: str, mode: str, year: Optional[str], source: str, summary: str,
            lines: List[str], limit: int, suggestions: Optional[List[str]] = None, **extra: Any) -> Dict[str, Any]:
    total = len(lines)
    shown = lines[:limit]
    found = status == "ok"
    out = {
        "status": status,
        "found": found,
        "verified": True,
        "revit_year": year,
        "docs": source,
        "query": query,
        "mode": mode,
        "summary": summary,
        "lines": shown,
        "total": total,
        "truncated": total > len(shown),
        "limit": limit,
    }
    if suggestions is not None:
        out["suggestions"] = suggestions
    out.update(extra)
    return out


def lookup(query: str, mode: str = "auto", limit: int = 20, revit_year: Optional[int] = None,
           doc_xml_path: Optional[str] = None, workspace: Any = None) -> Dict[str, Any]:
    q = str(query or "").strip()
    if q.endswith("()"):
        q = q[:-2]
    if "(" in q:
        q = q[: q.index("(")]
    mode = str(mode or "auto").lower()
    try:
        if not q:
            raise ValueError("query is empty")
        if len(q) > 200:
            raise ValueError("query is longer than 200 characters")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        limit = max(1, min(int(limit if limit is not None else 20), MAX_LIMIT))
        year = int(revit_year) if revit_year not in (None, "") else None
        if year is not None and year not in YEARS:
            raise ValueError("revit_year must be 2024, 2025, 2026 or 2027")
    except (TypeError, ValueError) as exc:
        return {"status": "error", "found": False, "verified": False, "error": f"bad input: {exc}", "query": q, "mode": mode}

    # 1. where the docs come from
    if doc_xml_path:
        if workspace is None or not getattr(workspace, "assert_in_workspace", None):
            return {"status": "error", "found": False, "verified": False, "query": q, "mode": mode,
                    "error": "doc_xml_path refused: no workspace is configured to check it against"}
        try:
            path = workspace.assert_in_workspace(Path(doc_xml_path))
        except Exception as exc:  # noqa: BLE001 - WorkspaceViolation or OS error
            return {"status": "error", "found": False, "verified": False, "query": q, "mode": mode,
                    "error": f"doc_xml_path refused: outside the workspace ({exc})"}
        if not Path(path).is_file():
            return {"status": "error", "found": False, "verified": False, "query": q, "mode": mode,
                    "error": f"doc_xml_path not found: {path}"}
        files = [Path(path)]
        yr = str(year) if year else _year_from_path(Path(path))
        origin = "doc_xml_path"
    else:
        yr, files, origin = find_docs(year)
        if not files:
            wanted = f"Revit {year}" if year else "Revit 2024-2027"
            msg = (f"No Revit API documentation found ({wanted}: no RevitAPI.xml next to the DLLs or in the NuGet cache). "
                   f"UNVERIFIED: cannot confirm '{q}'. Pass doc_xml_path to a RevitAPI.xml inside the workspace, "
                   "or test the member in a small revit_execute_python mode='read' script.")
            return {"status": "unverified", "found": False, "verified": False, "revit_year": None, "docs": "",
                    "query": q, "mode": mode, "summary": msg, "lines": [], "total": 0, "truncated": False, "limit": limit}
    label = f"Revit {yr or '(year unknown)'} API docs"
    source = f"{label}, {origin}: " + ", ".join(str(f) for f in files)

    try:
        index = load_index(files)
    except (OSError, ValueError, ET.ParseError) as exc:
        return {"status": "error", "found": False, "verified": False, "query": q, "mode": mode, "revit_year": yr,
                "docs": source, "error": f"could not read the documentation XML: {exc}"}

    if mode == "auto":
        if _resolve_types(index, q):
            mode = "type"
        elif any(t.startswith(q + ".") for t in index["types"]):
            mode = "namespace"
        elif "." in q:
            mode = "signature"
        else:
            mode = "member"
    args = (q, mode, yr, source, label, limit)
    if mode == "type":
        return _type_mode(index, *args)
    if mode == "namespace":
        return _namespace_mode(index, *args)
    return _member_mode(index, *args, signature=(mode == "signature"))


def _type_mode(index, q, mode, yr, source, label, limit):
    hits = _resolve_types(index, q)
    if not hits:
        cands = difflib.get_close_matches(_short(q), sorted({_short(t) for t in index["types"]}), n=8, cutoff=0.6)
        return _result("not_found", q, mode, yr, source, f"NOT FOUND in {label}: no type named '{q}'. Do not use it.",
                       [], limit, suggestions=cands)
    if len(hits) > 1:
        lines = [f"{index['types'][t][0]:8} {t}" for t in hits]
        return _result("ambiguous", q, mode, yr, source,
                       f"{len(hits)} types named '{q}' in {label}; repeat with a full name.", lines, limit)
    full = hits[0]
    kind, summary = index["types"][full]
    rows = index["members"].get(full, [])
    lines: List[str] = []
    seen: Dict[Tuple[str, str], int] = {}
    for r in rows:
        seen[(r[0], r[1])] = seen.get((r[0], r[1]), 0) + 1
    done = set()
    order = {"M": 1, "P": 2, "E": 3, "F": 0 if kind == "enum" else 4}
    for r in sorted(rows, key=lambda r: (r[1] != "#ctor", order.get(r[0], 9), r[1].lower())):
        k = (r[0], r[1])
        if k in done:
            continue
        done.add(k)
        n = seen[k]
        lines.append(_line(full, r, f"  [+{n - 1} overloads, see mode=signature]" if n > 1 else ""))
    head = f"{kind} {full} ({len(done)} members) in {label}"
    if summary:
        head += f": {summary}"
    if kind != "enum":
        head += " Inherited members are not listed (the docs XML has no inheritance)."
    return _result("ok", q, mode, yr, source, head, lines, limit, type=full, kind=kind,
                   namespace=_namespace(index, full))


def _member_mode(index, q, mode, yr, source, label, limit, signature):
    owners: Optional[List[str]] = None
    name = q
    if "." in q:
        tq, name = q.rsplit(".", 1)
        owners = _resolve_types(index, tq)
        if not owners:
            sug = difflib.get_close_matches(_short(tq), sorted({_short(t) for t in index["types"]}), n=5, cutoff=0.6)
            return _result("not_found", q, mode, yr, source,
                           f"NOT FOUND in {label}: no type named '{tq}'. Do not use it.", [], limit, suggestions=sug)
    low = name.lower()
    want_ctor = name in ("#ctor", "ctor", "new")
    hits: List[Tuple[str, list]] = []
    for owner, rows in index["members"].items():
        if owners is not None and owner not in owners:
            continue
        for r in rows:
            if r[1].lower() == low or (want_ctor and r[1] == "#ctor") or (owners and r[1] == "#ctor" and low == _short(owner).lower()):
                hits.append((owner, r))
    if not hits:
        elsewhere = []
        if owners:
            elsewhere = sorted({o for o, rows in index["members"].items() if any(r[1].lower() == low for r in rows)})
        if elsewhere:
            lines = [f"declared on {o}" for o in elsewhere]
            return _result(
                "not_on_type", q, mode, yr, source,
                f"'{name}' is not declared on {', '.join(_short(o) for o in owners)} in {label}, but on "
                f"{len(elsewhere)} other type(s). It may be inherited (the docs XML has no inheritance); check the base class.",
                lines, limit, suggestions=_suggest(index, name, owners))
        return _result("not_found", q, mode, yr, source,
                       f"NOT FOUND in {label}: '{q}' does not exist. Do not use it; pick a real name below.",
                       [], limit, suggestions=_suggest(index, name, owners))
    hits.sort(key=lambda h: (h[0], h[1][1], h[1][2] or ""))
    lines = []
    for owner, r in hits:
        if signature:
            lines.append(f"{_sig(owner, r)}  [{KIND_LABEL[r[0]] if r[0] != 'F' else 'value'} of {owner}]")
            if r[3]:
                lines.append(f"    {r[3]}")
        else:
            lines.append(f"{_line(owner, r)}  [{owner}]")
    n_types = len({h[0] for h in hits})
    word = "overload(s)" if signature else "match(es)"
    summary = f"{len(hits)} {word} of '{name}' on {n_types} type(s) in {label}."
    if any(r[0] == "M" for _, r in hits):
        summary += " Return types are not in the docs XML."
    return _result("ok", q, mode, yr, source, summary, lines, limit)


def _namespace_mode(index, q, mode, yr, source, label, limit):
    low = q.lower()
    spaces: Dict[str, List[str]] = {}
    for t in index["types"]:
        spaces.setdefault(_namespace(index, t), []).append(t)
    exact = [ns for ns in spaces if ns.lower() == low]
    if exact:
        ns = exact[0]
        lines = [f"{index['types'][t][0]:8} {_short(t)}" + (f"  - {index['types'][t][1]}" if index["types"][t][1] else "")
                 for t in sorted(spaces[ns], key=str.lower)]
        subs = sorted(s for s in spaces if s.lower().startswith(low + "."))
        lines += [f"namespace {s}" for s in subs]
        return _result("ok", q, mode, yr, source, f"namespace {ns}: {len(spaces[ns])} types in {label}.", lines, limit)
    near = sorted(s for s in spaces if low in s.lower())
    if near:
        lines = [f"namespace {s} ({len(spaces[s])} types)" for s in near]
        return _result("ok", q, mode, yr, source, f"{len(near)} namespaces contain '{q}' in {label}.", lines, limit)
    return _result("not_found", q, mode, yr, source, f"NOT FOUND in {label}: no namespace '{q}'.", [], limit,
                   suggestions=difflib.get_close_matches(q, sorted(spaces), n=5, cutoff=0.5))


class RevitApiModule:
    def lookup(
        self,
        query: str = "",
        mode: str = "auto",
        limit: int = 20,
        revit_year: Optional[int] = None,
        doc_xml_path: Optional[str] = None,
        workspace: Any = None,
        **_: Any,
    ) -> Dict[str, Any]:
        return lookup(query, mode=mode, limit=limit, revit_year=revit_year, doc_xml_path=doc_xml_path, workspace=workspace)
