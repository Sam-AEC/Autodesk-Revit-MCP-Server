#!/usr/bin/env python3
"""Generate THIRD_PARTY_NOTICES.md from real package metadata.

Sources (all read locally, nothing is fetched, so it runs offline):

* Python: the runtime dependency closure in packages/mcp-server-revit/uv.lock
  (names and locked versions). Licence, home page and licence file text come
  from importlib.metadata of the *installed* environment. Run it inside an
  environment synced from the lock (``uv sync --frozen``) for full data. A
  package that is not installed, or installed at a different version than the
  lock, is marked "unverified".
* NuGet: <PackageReference> items in packages/*/*.csproj (id, version,
  condition only). The licence column says "see package" unless a licence can
  be read from a local NuGet cache (NUGET_PACKAGES or ~/.nuget/packages); such
  a value is marked "unverified" because it is the package author's claim.
* npm: extensions/vscode/package.json and package-lock.json (licence strings
  come from the lock file; "dev only" means the package is not a runtime
  dependency of the extension).

The output is sorted and carries no timestamp, so the same inputs give the
same file. Use ``--check`` in CI to fail when the committed file is stale.

Usage: python scripts/generate_third_party_notices.py [--output PATH] [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "packages" / "mcp-server-revit" / "uv.lock"
ROOT_PROJECT = "aec-model-bridge"
VSCODE = ROOT / "extensions" / "vscode"
DEFAULT_OUTPUT = ROOT / "THIRD_PARTY_NOTICES.md"
UNVERIFIED = "unverified"
LICENCE_FILE_RE = re.compile(r"(^|/)(licen[sc]e|copying|notice|authors)[^/]*$", re.I)
MAX_LICENCE_TEXT = 40_000


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip() or "-"


# --------------------------------------------------------------------------- Python


def lock_runtime_closure() -> dict[str, str]:
    """Return {normalised name: locked version} for the runtime closure."""
    data = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    pkgs = {norm(p["name"]): p for p in data["package"]}
    todo = [norm(d["name"]) for d in pkgs[ROOT_PROJECT].get("dependencies", [])]
    seen: dict[str, str] = {}
    while todo:
        name = todo.pop()
        if name in seen or name not in pkgs:
            continue
        seen[name] = pkgs[name]["version"]
        todo.extend(norm(d["name"]) for d in pkgs[name].get("dependencies", []))
    return seen


def python_licence(dist: metadata.Distribution) -> str:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr.strip()
    classifiers = [
        c.split("::")[-1].strip()
        for c in (md.get_all("Classifier") or [])
        if c.startswith("License ::")
    ]
    classifiers = [c for c in classifiers if c != "OSI Approved"]
    if classifiers:
        return "; ".join(sorted(classifiers))
    lic = (md.get("License") or "").strip()
    if lic and "\n" not in lic and len(lic) <= 80:
        return lic
    return UNVERIFIED


def python_home(dist: metadata.Distribution) -> str:
    md = dist.metadata
    if md.get("Home-page"):
        return md["Home-page"].strip()
    urls = {}
    for entry in md.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        urls[label.strip().lower()] = url.strip()
    for key in ("homepage", "home", "source", "repository", "documentation"):
        if key in urls:
            return urls[key]
    return next(iter(urls.values()), "-")


def python_licence_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    out = []
    for f in sorted(dist.files or [], key=lambda p: p.as_posix()):
        posix = f.as_posix()
        if "dist-info" not in posix and ".egg-info" not in posix:
            continue
        if not LICENCE_FILE_RE.search(posix) or posix.endswith("AUTHORS"):
            continue
        try:
            text = f.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if text:
            out.append((posix.split("/")[-1], text[:MAX_LICENCE_TEXT]))
    return out


def python_section() -> list[str]:
    closure = lock_runtime_closure()
    rows, texts = [], []
    for name in sorted(closure):
        locked = closure[name]
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            rows.append((name, locked, f"{UNVERIFIED} (not installed)", "-"))
            continue
        lic, home = python_licence(dist), python_home(dist)
        if dist.version != locked:
            lic = f"{UNVERIFIED} (installed {dist.version}, lock {locked}; read as {lic})"
        elif lic == UNVERIFIED:
            lic = f"{UNVERIFIED} (no licence field in package metadata)"
        rows.append((name, locked, lic, home))
        for fname, text in python_licence_texts(dist):
            texts.append((name, locked, fname, text))
    lines = [
        "## Python packages (runtime)",
        "",
        "Source: `packages/mcp-server-revit/uv.lock`, runtime closure of the `aec-model-bridge` "
        "project (development extras are not included). Licence data comes from the installed "
        "package metadata. Check the locked version before relying on a row marked "
        f"`{UNVERIFIED}`. Some packages are only installed on some platforms or Python versions.",
        "",
        "| Package | Locked version | Licence | Home page |",
        "|---|---|---|---|",
    ]
    lines += [f"| {cell(n)} | {cell(v)} | {cell(l)} | {cell(h)} |" for n, v, l, h in rows]
    lines += ["", f"{len(rows)} packages.", ""]
    if texts:
        lines += [
            "### Licence texts shipped with the Python packages",
            "",
            "Copied from the licence files in each installed package. Packages that ship no "
            "licence file are not listed here.",
            "",
        ]
        for name, version, fname, text in texts:
            fence = "~~~~"
            lines += [
                f"<details><summary>{name} {version}: {fname}</summary>",
                "",
                fence + "text",
                text,
                fence,
                "",
                "</details>",
                "",
            ]
    return lines


# --------------------------------------------------------------------------- NuGet


def nuget_cache_dirs() -> list[Path]:
    dirs = []
    env = os.environ.get("NUGET_PACKAGES")
    if env:
        dirs.append(Path(env))
    dirs.append(Path.home() / ".nuget" / "packages")
    return [d for d in dirs if d.is_dir()]


def nuget_cache_licence(pkg_id: str, version: str) -> str | None:
    if "*" in version or "$(" in version:
        return None
    for base in nuget_cache_dirs():
        nuspec = base / pkg_id.lower() / version.lower() / f"{pkg_id.lower()}.nuspec"
        if not nuspec.is_file():
            continue
        try:
            tree = ET.parse(nuspec)
        except ET.ParseError:
            continue
        for el in tree.iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "license" and (el.text or "").strip():
                return el.text.strip()
        for el in tree.iter():
            if el.tag.rsplit("}", 1)[-1] == "licenseUrl" and (el.text or "").strip():
                return el.text.strip()
    return None


def nuget_section() -> list[str]:
    rows = set()
    for csproj in sorted((ROOT / "packages").glob("*/*.csproj")):
        rel = csproj.relative_to(ROOT).as_posix()
        tree = ET.parse(csproj)
        for el in tree.iter("PackageReference"):
            pid = el.get("Include")
            if not pid:
                continue
            version = el.get("Version") or "-"
            cond = el.get("Condition") or ""
            m = re.search(r"TargetFramework\)'(==|!=)'([^']+)'", cond)
            only = "" if not m else (f"{m.group(2)} only" if m.group(1) == "==" else f"not {m.group(2)}")
            rows.add((pid, version, only, rel))
    lines = [
        "## NuGet packages (.NET add-ins and tools)",
        "",
        "Source: `<PackageReference>` items in `packages/*/*.csproj`. Only the package id and "
        "version are read from the repository. The licence column says `see package` unless a "
        "licence could be read from a local NuGet cache on the machine that ran the generator; "
        f"such a value is the package author's own claim and is marked `{UNVERIFIED}`.",
        "",
        "| Package | Version | Applies to | Licence | Project |",
        "|---|---|---|---|---|",
    ]
    for pid, version, only, rel in sorted(rows, key=lambda r: (r[0].lower(), r[1], r[3])):
        found = nuget_cache_licence(pid, version)
        lic = f"{found} ({UNVERIFIED}, from local NuGet cache)" if found else "see package"
        lines.append(f"| {cell(pid)} | {cell(version)} | {cell(only or "all targets")} | {cell(lic)} | `{rel}` |")
    lines += [
        "",
        "The Revit, Navisworks and Rhino host assemblies (`RevitAPI.dll`, `RevitAPIUI.dll`, "
        "`Autodesk.Navisworks.*`) are referenced from the user's own installation and are not "
        "distributed. See [TRADEMARKS.md](TRADEMARKS.md).",
        "",
    ]
    return lines


# --------------------------------------------------------------------------- npm


def npm_section() -> list[str]:
    pkg = json.loads((VSCODE / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((VSCODE / "package-lock.json").read_text(encoding="utf-8"))
    runtime_roots = set(pkg.get("dependencies", {}))
    entries = {
        k[len("node_modules/") :] if k.startswith("node_modules/") else k: v
        for k, v in lock["packages"].items()
        if k
    }
    # Nested paths such as a/node_modules/b: keep the last segment path as name.
    def pkg_name(path: str) -> str:
        return path.split("node_modules/")[-1]

    rows = {}
    for path, info in entries.items():
        name = pkg_name(path)
        lic = info.get("license")
        if isinstance(lic, dict):
            lic = lic.get("type")
        if isinstance(lic, list):
            lic = " OR ".join(str(x) for x in lic)
        lic = lic or f"{UNVERIFIED} (no licence field in lock file)"
        if lic.upper().startswith("SEE LICENSE"):
            lic = f"{lic} ({UNVERIFIED}, licence is in a file, not an SPDX id)"
        scope = "dev only" if info.get("dev") else "runtime"
        if info.get("optional") and info.get("dev"):
            scope = "dev only (optional)"
        rows[(name.lower(), info.get("version", "-"))] = (name, info.get("version", "-"), lic, scope)
    runtime = [r for r in rows.values() if r[3] == "runtime"]
    dev = [r for r in rows.values() if r[3] != "runtime"]
    lines = [
        "## npm packages (VS Code extension)",
        "",
        f"Source: `extensions/vscode/package.json` and `package-lock.json`. Licence strings are "
        f"taken from the lock file. The extension declares {len(runtime_roots)} runtime "
        "dependencies and is packaged with `vsce package --no-dependencies`; the TypeScript is "
        "bundled by esbuild. Packages marked dev only are build and test tools and are not "
        "shipped in the extension. If a runtime import is ever added, re-check the bundle.",
        "",
        f"Runtime packages in the lock file: {len(runtime)}. Dev-only packages: {len(dev)}.",
        "",
    ]
    if runtime:
        lines += ["### Runtime", "", "| Package | Version | Licence |", "|---|---|---|"]
        lines += [f"| {cell(n)} | {cell(v)} | {cell(l)} |" for n, v, l, _ in sorted(runtime, key=lambda r: (r[0].lower(), r[1]))]
        lines.append("")
    # Summarise dev-only packages by licence, then list direct dev dependencies.
    by_lic: dict[str, int] = {}
    for _, _, lic, _ in dev:
        by_lic[lic] = by_lic.get(lic, 0) + 1
    direct = sorted(pkg.get("devDependencies", {}))
    lines += ["### Dev only", "", "Direct development dependencies:", "",
              "| Package | Version | Licence |", "|---|---|---|"]
    for name in direct:
        row = rows.get((name.lower(), entries.get(f"{name}", {}).get("version", "-")))
        if row:
            lines.append(f"| {cell(row[0])} | {cell(row[1])} | {cell(row[2])} |")
        else:
            lines.append(f"| {cell(name)} | - | {UNVERIFIED} (not in lock file) |")
    lines += ["", "All dev-only packages in the lock file, counted by licence string:", "",
              "| Licence | Packages |", "|---|---|"]
    lines += [f"| {cell(l)} | {c} |" for l, c in sorted(by_lic.items(), key=lambda kv: (-kv[1], kv[0]))]
    lines.append("")
    return lines


# --------------------------------------------------------------------------- document


HEADER = f"""# Third-party notices

AEC Model Bridge is licensed under GPL-3.0-or-later with the Revit Linking Exception,
or under a commercial licence (see [LICENSING.md](LICENSING.md)). It uses the
third-party components below, each under its own licence. This file is generated by
`scripts/generate_third_party_notices.py` from package metadata. Do not edit it by hand;
regenerate it after a dependency change.

Entries marked `{UNVERIFIED}` could not be read from package metadata, or came from a
different version than the one locked. Check them against the package itself before
you rely on them. This file is an engineering inventory, not legal advice.

## LGPL notice: IfcOpenShell

IfcOpenShell is licensed under the GNU Lesser General Public License, version 3 or
later. The Windows installer installs it unmodified as ordinary Python files in
`C:\\ProgramData\\AECModelBridge\\python\\Lib\\site-packages\\ifcopenshell`, so you can replace
it with another version of the library (for example with
`python.exe -m pip install --upgrade ifcopenshell` from the bundled Python). The LGPL-3.0 text is in [LICENSES/LGPL-3.0.txt](LICENSES/LGPL-3.0.txt) (installed to
`C:\\ProgramData\\AECModelBridge\\LICENSES`) and the GPL-3.0 text is in [LICENSE](LICENSE).
The IfcOpenShell wheel itself ships no licence file. Source code for IfcOpenShell is available from
<https://github.com/IfcOpenShell/IfcOpenShell>; the version in `uv.lock` is listed in the
Python table below (the installer build runs `pip install` without the lock file, so the
bundled version is the one in `python\\Lib\\site-packages\\ifcopenshell-*.dist-info`).
See [NOTICE](NOTICE).
"""


def build() -> str:
    parts = [HEADER, *python_section(), *nuget_section(), *npm_section()]
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--check", action="store_true", help="exit 1 if the file is out of date")
    args = ap.parse_args()
    text = build()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{args.output} is out of date; run scripts/generate_third_party_notices.py", file=sys.stderr)
            return 1
        return 0
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.output} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
