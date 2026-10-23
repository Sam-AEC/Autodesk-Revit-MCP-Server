"""Static contract between the C# add-ins and the Python hub.

CI only compiles the add-ins and there is no C# test project, so nothing else
notices when the two sides drift apart. This module parses the add-in sources
with regular expressions (no .NET needed) and checks them against the hub's
provider tools.

What is covered:

1. Approval-gate coverage: every add-in command declared ``IsMutating = true``
   (the attribute default is true) whose hub tool is registered must also be
   ``is_mutating`` in the hub, otherwise ``ApprovalGate`` never sees the call.
   Mutating add-in commands that no hub tool forwards to are checked separately.
2. No dangling names: every add-in command a hub provider forwards exists in the
   add-in catalog (Revit, Navisworks; Rhino ``case`` labels).
3. No add-in command name is declared twice (the catalog is a dictionary keyed
   by name, so a duplicate silently shadows the first handler).
4. A heuristic source guard: a C# method must not call itself with the same
   arity unless an overload with that arity exists (this is how
   ``CreateTransaction`` once recursed forever).

Known mismatches are recorded in the ``KNOWN_*`` allowlists below, with a reason
each. The tests pass today and fail on any NEW mismatch, and also when an
allowlist entry stops being true so the list cannot rot.

UNVERIFIED: nothing here runs Revit, Navisworks or Rhino.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from revit_mcp_server.providers import NavisworksProvider, RevitProvider, RhinoProvider
from revit_mcp_server.security.workspace import WorkspaceMonitor

PACKAGES = Path(__file__).resolve().parents[2]
REVIT_SRC = PACKAGES / "revit-bridge-addin" / "src"
NAVIS_SRC = PACKAGES / "navisworks-bridge-addin" / "src"
RHINO_SRC = PACKAGES / "rhino-bridge-addin" / "src"

# --------------------------------------------------------------------------- #
# Known gaps. Each entry is a real mismatch found when this test was written.
# Do not add to these lists to make a new failure go away; fix the metadata.
# --------------------------------------------------------------------------- #

# (provider, hub tool, add-in command): add-in says IsMutating=true, hub tool is not
# is_mutating, so the approval gate does not cover it.
KNOWN_UNGATED = {
    # navisworks.py enrich verbs {set, invoke, delete, create, move, copy, rotate,
    # mirror, run} do not include append / refresh / activate. append_file changes
    # the open model; refresh reloads linked files; activate_viewpoint moves the view.
    ("navisworks", "navisworks_append_file", "navis.append_file"),
    ("navisworks", "navisworks_refresh", "navis.refresh"),
    ("navisworks", "navisworks_activate_viewpoint", "navis.activate_viewpoint"),
    # revit.py verbs do not include render / calculate / reflect. The add-in flag may
    # be over-cautious for these two (they are probably read or export only); needs a
    # decision with a Revit run before either side is changed.
    ("revit", "revit_render_3d", "revit.render_3d_view"),
    ("revit", "revit_calculate_material_quantities", "revit.calculate_material_quantities"),
    # reflect_get only reads a property but the add-in marks it mutating.
    ("revit", "revit_reflect_get", "revit.reflect_get"),
}

# (provider, add-in command): IsMutating=true commands that no hub tool forwards to.
# Not reachable through MCP, so not a gate hole; recorded so a new one is noticed.
KNOWN_UNMAPPED_MUTATING = {
    ("revit", "revit.open_document"),
    ("revit", "revit.create_cable_tray"),
    ("revit", "revit.create_revision_cloud"),
    ("revit", "revit.create_text_type"),
}

# Rhino has no attribute catalog: commands are ``case "name":`` labels in one switch,
# with no mutating flag, so the check is by hub tool name (see the test below).
KNOWN_RHINO_UNGATED = {
    # GenerateDiagridTower bakes Breps and creates layers/materials
    # (rhino-bridge-addin/src/BridgeCommands.cs); rhino.py verbs lack "generate".
    "rhino_generate_diagrid_tower",
}


# --------------------------------------------------------------------------- #
# C# parsing
# --------------------------------------------------------------------------- #
_ATTR = re.compile(r'\[BridgeCommand\(\s*"([^"]+)"([^\]]*)\)\]')
_FLAG = r"{}\s*=\s*(true|false)"


def parse_commands(source: str) -> list[dict]:
    """Return one dict per [BridgeCommand(...)] in ``source``."""
    found = []
    for m in _ATTR.finditer(source):
        args = m.group(2)
        mut = re.search(_FLAG.format("IsMutating"), args)
        conf = re.search(_FLAG.format("ConfirmationRequired"), args)
        found.append(
            {
                "name": m.group(1),
                # BridgeCommandAttribute defaults: IsMutating = true, ConfirmationRequired = false
                "mutating": mut.group(1) == "true" if mut else True,
                "confirm": conf.group(1) == "true" if conf else False,
            }
        )
    return found


def load_commands(root: Path) -> list[dict]:
    out = []
    for path in sorted(root.rglob("*.cs")):
        for cmd in parse_commands(path.read_text(encoding="utf-8")):
            out.append({**cmd, "file": path.relative_to(PACKAGES).as_posix()})
    return out


def strip_strings_and_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r'@"(?:[^"]|"")*"', '""', src)
    src = re.sub(r'\$?"(?:\\.|[^"\\\n])*"', '""', src)
    return re.sub(r"'(?:\\.|[^'\\])'", "''", src)


_DECL = re.compile(
    r"(?:public|private|internal|protected)\s+(?:static\s+)?(?:async\s+)?[\w<>\[\]?,.]+\s+(\w+)\s*\(([^()]*)\)\s*\{"
)


def _split_args(text: str) -> list[str]:
    depth, cur, parts = 0, "", []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def find_self_calls(source: str) -> list[str]:
    """Methods that call themselves, unconditionally, with their own arity.

    Heuristic, deliberately narrow so it does not flag real recursion (tree walks
    call themselves inside a loop or an ``if``): only a call at the top level of
    the method body counts, qualified by nothing, ``this`` or the declaring class,
    and only when the name has no overload of a different arity in the file."""
    src = strip_strings_and_comments(source)
    classes = [(m.start(), m.group(1)) for m in re.finditer(r"\bclass\s+(\w+)", src)]
    decls = [(m.group(1), len(_split_args(m.group(2))), m.end(), m.start()) for m in _DECL.finditer(src)]
    arities: dict[str, set[int]] = {}
    for name, arity, _, _ in decls:
        arities.setdefault(name, set()).add(arity)
    problems = set()
    for name, arity, body_start, decl_pos in decls:
        if len(arities[name]) != 1:
            continue
        owner = next((c for pos, c in reversed(classes) if pos < decl_pos), None)
        depth, i, top = 1, body_start, []
        while i < len(src) and depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            top.append(src[i] if depth == 1 else " ")
            i += 1
        body = "".join(top)
        for call in re.finditer(r"(?<![\w.])(?:(this|[A-Z]\w*)\.)?" + re.escape(name) + r"\s*\(", body):
            if call.group(1) not in (None, "this", owner):
                continue
            if body[max(0, call.start() - 4) : call.start()].endswith("new "):
                continue
            j, d = call.end(), 1
            while j < len(body) and d:
                d += {"(": 1, ")": -1}.get(body[j], 0)
                j += 1
            if len(_split_args(body[call.end() : j - 1])) == arity:
                problems.add(f"{name}/{arity}")
    return sorted(problems)


# --------------------------------------------------------------------------- #
# Hub fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def workspace():
    return WorkspaceMonitor([Path(tempfile.mkdtemp(prefix="contract-ws-"))])


@pytest.fixture(scope="module")
def surfaces(workspace):
    """provider name -> (add-in commands, provider instance)."""
    return {
        "revit": (load_commands(REVIT_SRC), RevitProvider(workspace=workspace)),
        "navisworks": (load_commands(NAVIS_SRC), NavisworksProvider(workspace=workspace)),
    }


def _hub_tools(provider):
    return {t.name: t for t in provider.get_capabilities()}


# --------------------------------------------------------------------------- #
# Sanity: the parser really sees the add-ins
# --------------------------------------------------------------------------- #
def test_parser_finds_the_catalogs(surfaces):
    assert len(surfaces["revit"][0]) > 100
    assert len(surfaces["navisworks"][0]) >= 15


def test_parser_defaults_and_flags():
    cmds = parse_commands(
        '[BridgeCommand("a.one")]\n'
        '[BridgeCommand("a.two", IsMutating = false)]\n'
        '[BridgeCommand("a.three", IsMutating = true, ConfirmationRequired = true)]\n'
    )
    assert [(c["name"], c["mutating"], c["confirm"]) for c in cmds] == [
        ("a.one", True, False),
        ("a.two", False, False),
        ("a.three", True, True),
    ]


# --------------------------------------------------------------------------- #
# (3) duplicates
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("provider", ["revit", "navisworks"])
def test_no_command_declared_twice(surfaces, provider):
    names = [c["name"] for c in surfaces[provider][0]]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"{provider} add-in declares these command names more than once: {dupes}"


# --------------------------------------------------------------------------- #
# (2) no dangling names
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("provider", ["revit", "navisworks"])
def test_every_forwarded_command_exists_in_addin(surfaces, provider):
    commands, prov = surfaces[provider]
    catalog = {c["name"] for c in commands}
    dangling = {tool: cmd for tool, (cmd, _) in prov._tool_mapping.items() if cmd not in catalog}
    assert not dangling, f"{provider} hub forwards to add-in commands that do not exist: {dangling}"


@pytest.mark.parametrize("provider", ["revit", "navisworks"])
def test_every_hub_tool_has_a_mapping(surfaces, provider):
    _, prov = surfaces[provider]
    unmapped = sorted(set(_hub_tools(prov)) - set(prov._tool_mapping))
    stale = sorted(set(prov._tool_mapping) - set(_hub_tools(prov)))
    assert not unmapped, f"{provider} tools with no add-in mapping: {unmapped}"
    assert not stale, f"{provider} mappings with no declared tool: {stale}"


def test_rhino_forwarded_commands_exist_in_addin(workspace):
    source = (RHINO_SRC / "BridgeCommands.cs").read_text(encoding="utf-8")
    # "health" is served by the HTTP /health route in BridgeServer.cs, not a switch case.
    cases = set(re.findall(r'case\s+"([^"]+)"\s*:', source)) | {"health"}
    assert 'AbsolutePath == "/health"' in (RHINO_SRC / "BridgeServer.cs").read_text(encoding="utf-8")
    prov = RhinoProvider(workspace=workspace)
    dangling = {t: cmd for t, (cmd, _) in prov._tool_mapping.items() if cmd not in cases}
    assert not dangling, f"rhino hub forwards to commands with no case label: {dangling}"


# --------------------------------------------------------------------------- #
# (1) approval-gate coverage
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("provider", ["revit", "navisworks"])
def test_mutating_addin_commands_are_gated_in_hub(surfaces, provider):
    commands, prov = surfaces[provider]
    mutating = {c["name"] for c in commands if c["mutating"]}
    tools = _hub_tools(prov)
    ungated = {
        (provider, tool, cmd)
        for tool, (cmd, _) in prov._tool_mapping.items()
        if cmd in mutating and tool in tools and not tools[tool].is_mutating
    }
    known = {g for g in KNOWN_UNGATED if g[0] == provider}
    assert ungated - known == set(), (
        "New mutating add-in commands whose hub tool is not is_mutating (approval gate bypass): "
        f"{sorted(ungated - known)}"
    )
    assert known - ungated == set(), (
        f"KNOWN_UNGATED entries that are no longer true, remove them: {sorted(known - ungated)}"
    )


@pytest.mark.parametrize("provider", ["revit", "navisworks"])
def test_mutating_addin_commands_without_hub_tool(surfaces, provider):
    commands, prov = surfaces[provider]
    forwarded = {cmd for cmd, _ in prov._tool_mapping.values()}
    unmapped = {(provider, c["name"]) for c in commands if c["mutating"] and c["name"] not in forwarded}
    known = {g for g in KNOWN_UNMAPPED_MUTATING if g[0] == provider}
    assert unmapped - known == set(), f"New mutating add-in commands with no hub tool: {sorted(unmapped - known)}"
    assert known - unmapped == set(), f"KNOWN_UNMAPPED_MUTATING entries no longer true: {sorted(known - unmapped)}"


def test_rhino_write_tools_are_gated(workspace):
    """Rhino's add-in has no mutating flag, so judge by what the hub tool name says:
    any tool carrying a write verb must be is_mutating."""
    write_verbs = {
        "create", "delete", "move", "set", "place", "append", "generate", "execute",
        "import", "rename", "purge", "clear", "transform", "boolean", "run", "invoke",
    }
    tools = _hub_tools(RhinoProvider(workspace=workspace))
    ungated = {n for n, t in tools.items() if write_verbs & set(n.split("_")) and not t.is_mutating}
    assert ungated - KNOWN_RHINO_UNGATED == set(), f"New ungated Rhino write tools: {sorted(ungated - KNOWN_RHINO_UNGATED)}"
    assert KNOWN_RHINO_UNGATED - ungated == set(), "KNOWN_RHINO_UNGATED entry no longer true, remove it"


# --------------------------------------------------------------------------- #
# (4) source guard
# --------------------------------------------------------------------------- #
def test_self_call_detector_catches_the_createtransaction_bug():
    bad = """
    public static class BridgeCommandFactory {
    public static Transaction CreateTransaction(Document doc, string name)
    {
        var txName = $"AMB: {name}";
        return BridgeCommandFactory.CreateTransaction(doc, txName);
    }
    }
    """
    assert find_self_calls(bad) == ["CreateTransaction/2"]
    good = bad.replace("BridgeCommandFactory.CreateTransaction(doc, txName)", "new Transaction(doc, txName)")
    assert find_self_calls(good) == []
    overload = "static int F(int a) { return F(a, 1); }\nstatic int F(int a, int b) { return a + b; }"
    assert find_self_calls(overload) == []


def test_no_csharp_method_calls_itself_with_same_arity():
    problems = {}
    for root in (REVIT_SRC, NAVIS_SRC, RHINO_SRC):
        for path in sorted(root.rglob("*.cs")):
            found = find_self_calls(path.read_text(encoding="utf-8"))
            if found:
                problems[path.relative_to(PACKAGES).as_posix()] = found
    assert not problems, f"C# methods that appear to call themselves with their own signature: {problems}"
