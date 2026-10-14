from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest
from revit_mcp_server.modules.revit_api import module as api
from revit_mcp_server.providers.module_provider import ModuleProvider
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.workspace import WorkspaceMonitor

MODULE_DIR = Path(api.__file__).parent

FIXTURE = """<?xml version="1.0"?>
<doc>
  <assembly>"RevitAPI"</assembly>
  <members>
    <member name="T:Autodesk.Revit.DB.Wall"><summary>Represents a wall in Autodesk Revit.</summary></member>
    <member name="M:Autodesk.Revit.DB.Wall.Create(Autodesk.Revit.DB.Document,Autodesk.Revit.DB.Curve,Autodesk.Revit.DB.ElementId,System.Boolean)">
      <summary>Creates a new rectangular profile wall using the default wall style.</summary>
      <param name="document">The document.</param><param name="curve">The base line.</param>
      <param name="levelId">The level.</param><param name="structural">Structural or not.</param>
    </member>
    <member name="M:Autodesk.Revit.DB.Wall.Create(Autodesk.Revit.DB.Document,System.Collections.Generic.IList{Autodesk.Revit.DB.Curve},System.Boolean)">
      <summary>Creates a profile wall from <see cref="T:Autodesk.Revit.DB.Curve" /> loops.</summary>
      <param name="document">The document.</param><param name="profile">The curves.</param><param name="structural">Structural.</param>
    </member>
    <member name="P:Autodesk.Revit.DB.Wall.Flipped"><summary>The wall is flipped.</summary></member>
    <member name="P:Autodesk.Revit.DB.Wall.Orientation"><summary>The normal of the exterior side.</summary></member>
    <member name="M:Autodesk.Revit.DB.Wall.Flip"><summary>Flips the wall.</summary></member>
    <member name="T:Autodesk.Revit.DB.WallLocationLine"><summary>Wall location line options.</summary></member>
    <member name="F:Autodesk.Revit.DB.WallLocationLine.WallCenterline"><summary>Center of the wall.</summary></member>
    <member name="F:Autodesk.Revit.DB.WallLocationLine.CoreCenterline"><summary>Center of the core.</summary></member>
    <member name="F:Autodesk.Revit.DB.WallLocationLine.FinishFaceExterior"><summary>Exterior finish face.</summary></member>
    <member name="T:Autodesk.Revit.DB.FamilyInstance"><summary>A family instance.</summary></member>
    <member name="M:Autodesk.Revit.DB.FamilyInstance.GetSubComponentElementIds"><summary>Sub component ids.</summary></member>
    <member name="P:Autodesk.Revit.DB.FamilyInstance.Symbol"><summary>The family type.</summary></member>
    <member name="T:Autodesk.Revit.DB.Element"><summary>Base class.</summary></member>
    <member name="P:Autodesk.Revit.DB.Element.Name"><summary>The element name.</summary></member>
    <member name="M:Autodesk.Revit.DB.Element.GetDependentElements(Autodesk.Revit.DB.ElementFilter)">
      <summary>Dependent elements.</summary><param name="filter">A filter or null.</param>
    </member>
    <member name="M:Autodesk.Revit.DB.XYZ.#ctor(System.Double,System.Double,System.Double)">
      <summary>Creates an XYZ.</summary><param name="x">X.</param><param name="y">Y.</param><param name="z">Z.</param>
    </member>
    <member name="T:Autodesk.Revit.DB.Structure.StructuralType"><summary>Structural type.</summary></member>
    <member name="F:Autodesk.Revit.DB.Structure.StructuralType.NonStructural"><summary>Not structural.</summary></member>
    <member name="F:Autodesk.Revit.DB.Structure.StructuralType.Beam"><summary>A beam.</summary></member>
  </members>
</doc>
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """No real Revit or NuGet: an installed 'Revit 2026' holding the fixture, an empty NuGet cache, a temp cache dir."""
    pf = tmp_path / "pf"
    folder = pf / "Autodesk" / "Revit 2026"
    folder.mkdir(parents=True)
    (folder / "RevitAPI.xml").write_text(FIXTURE, encoding="utf-8")
    monkeypatch.setattr(api, "_program_files", lambda: [pf])
    monkeypatch.setattr(api, "_nuget_roots", lambda: [tmp_path / "nuget"])
    monkeypatch.setattr(api, "cache_dir", lambda: tmp_path / "cache")
    api._LOADED.clear()
    yield tmp_path
    api._LOADED.clear()


def test_type_mode_lists_members_and_groups_overloads(env):
    r = api.lookup("Wall", mode="type")
    assert r["status"] == "ok" and r["found"] and r["revit_year"] == "2026"
    assert r["type"] == "Autodesk.Revit.DB.Wall" and r["kind"] == "type"
    assert "Revit 2026" in r["summary"]
    text = "\n".join(r["lines"])
    assert "Wall.Create(Document document, Curve curve, ElementId levelId, Boolean structural)" in text
    assert "[+1 overloads" in text and "Wall.Flipped" in text
    assert len(r["lines"]) == 4


def test_type_mode_enum_values(env):
    r = api.lookup("StructuralType")
    assert r["mode"] == "type" and r["kind"] == "enum" and r["namespace"] == "Autodesk.Revit.DB.Structure"
    assert r["lines"][0].startswith("value") and any("StructuralType.Beam" in x for x in r["lines"])


def test_member_mode_found_and_not_found_with_suggestions(env):
    r = api.lookup("GetDependentElements", mode="member")
    assert r["status"] == "ok" and "Element.GetDependentElements(ElementFilter filter)" in r["lines"][0]
    miss = api.lookup("GetSubComponentIds", mode="member")
    assert miss["status"] == "not_found" and miss["found"] is False and miss["lines"] == []
    assert "NOT FOUND in Revit 2026" in miss["summary"]
    assert "FamilyInstance.GetSubComponentElementIds" in miss["suggestions"]
    scoped = api.lookup("FamilyInstance.GetSubComponentIds", mode="member")
    assert scoped["status"] == "not_found" and scoped["suggestions"][0] == "FamilyInstance.GetSubComponentElementIds"


def test_member_on_wrong_type_points_at_declaring_type(env):
    r = api.lookup("FamilyInstance.Name", mode="member")
    assert r["status"] == "not_on_type" and r["found"] is False
    assert r["lines"] == ["declared on Autodesk.Revit.DB.Element"] and "inherited" in r["summary"]


def test_signature_mode_returns_every_overload(env):
    r = api.lookup("Wall.Create()", mode="signature")
    assert r["status"] == "ok" and "2 overload(s)" in r["summary"] and "Return types" in r["summary"]
    sigs = [x for x in r["lines"] if not x.startswith(" ")]
    assert sigs[0].startswith("Wall.Create(Document document, Curve curve, ElementId levelId, Boolean structural)")
    assert sigs[1].startswith("Wall.Create(Document document, IList<Curve> profile, Boolean structural)")
    assert "    Creates a profile wall from Curve loops." in r["lines"]
    ctor = api.lookup("XYZ.XYZ", mode="signature")
    assert ctor["lines"][0].startswith("new XYZ(Double x, Double y, Double z)")


def test_namespace_mode(env):
    r = api.lookup("Autodesk.Revit.DB.Structure", mode="namespace")
    assert r["status"] == "ok" and r["lines"][0].startswith("enum") and "StructuralType" in r["lines"][0]
    top = api.lookup("Autodesk.Revit.DB")
    assert top["mode"] == "namespace" and "namespace Autodesk.Revit.DB.Structure" in top["lines"]


def test_truncation_flag(env):
    r = api.lookup("Wall", mode="type", limit=2)
    assert r["truncated"] is True and len(r["lines"]) == 2 and r["total"] == 4


def test_index_is_cached_in_user_cache_dir(env):
    api.lookup("Wall")
    cached = list((env / "cache").glob("index-*.json.gz"))
    assert len(cached) == 1
    api._LOADED.clear()
    real_parse = api.parse_files
    api.parse_files = lambda files: pytest.fail("cache was not used")
    try:
        assert api.lookup("Wall.Flip", mode="signature")["status"] == "ok"
    finally:
        api.parse_files = real_parse


def test_doc_xml_path_inside_workspace_is_used_and_outside_is_refused(env, tmp_path):
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "Revit 2025 RevitAPI.xml").write_text(FIXTURE, encoding="utf-8")
    ws = WorkspaceMonitor([ws_dir])
    ok = api.lookup("Wall.Flip", doc_xml_path=str(ws_dir / "Revit 2025 RevitAPI.xml"), workspace=ws)
    assert ok["status"] == "ok" and ok["revit_year"] == "2025" and "doc_xml_path" in ok["docs"]
    outside = api.lookup("Wall.Flip", doc_xml_path=str(env / "pf" / "Autodesk" / "Revit 2026" / "RevitAPI.xml"), workspace=ws)
    assert outside["status"] == "error" and "refused" in outside["error"]
    assert api.lookup("Wall", doc_xml_path="x.xml", workspace=None)["status"] == "error"


def test_entity_declarations_are_refused(env, tmp_path):
    ws_dir = tmp_path / "ws2"
    ws_dir.mkdir()
    (ws_dir / "RevitAPI.xml").write_text('<?xml version="1.0"?><!DOCTYPE doc [<!ENTITY a "x">]><doc/>', encoding="utf-8")
    r = api.lookup("Wall", doc_xml_path=str(ws_dir / "RevitAPI.xml"), workspace=WorkspaceMonitor([ws_dir]))
    assert r["status"] == "error" and "DOCTYPE" in r["error"]


def test_missing_docs_is_unverified(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_program_files", lambda: [tmp_path / "none"])
    monkeypatch.setattr(api, "_nuget_roots", lambda: [tmp_path / "none"])
    api._LOADED.clear()
    r = api.lookup("Wall.Create")
    assert r["status"] == "unverified" and r["verified"] is False and r["found"] is False
    assert "No Revit API documentation found" in r["summary"] and "UNVERIFIED" in r["summary"]


def test_nuget_fallback_and_year_selection(tmp_path, monkeypatch):
    nuget = tmp_path / "nuget"
    for ver in ("2025.4.60", "2027.3.0"):
        d = nuget / "nice3point.revit.api.revitapi" / ver / "ref" / "net8.0-windows7.0"
        d.mkdir(parents=True)
        (d / "RevitAPI.xml").write_text(FIXTURE, encoding="utf-8")
    monkeypatch.setattr(api, "_program_files", lambda: [tmp_path / "none"])
    monkeypatch.setattr(api, "_nuget_roots", lambda: [nuget])
    monkeypatch.setattr(api, "cache_dir", lambda: tmp_path / "cache")
    api._LOADED.clear()
    assert api.lookup("Wall")["revit_year"] == "2027"
    r = api.lookup("Wall", revit_year=2025)
    assert r["revit_year"] == "2025" and "NuGet cache" in r["docs"]
    assert api.lookup("Wall", revit_year=2024)["status"] == "unverified"


def test_bad_input(env):
    assert api.lookup("", mode="type")["status"] == "error"
    assert api.lookup("Wall", mode="guess")["status"] == "error"
    assert api.lookup("Wall", revit_year=2019)["status"] == "error"


def test_registered_read_only_tool_runs_without_plan(env, tmp_path):
    manifest = ModuleManifest(**json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8")))
    inst = ModuleInstance(manifest, MODULE_DIR)
    inst.code_module._program_files = api._program_files
    inst.code_module._nuget_roots = api._nuget_roots
    inst.code_module.cache_dir = api.cache_dir
    modules = SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False))
    provider = ModuleProvider(modules, WorkspaceMonitor([tmp_path]))
    caps = {t.name: t for t in provider.get_capabilities()}
    tool = caps["revit_api_lookup"]
    assert tool.is_mutating is False
    for prop in tool.input_schema["properties"].values():
        assert prop.get("description")
    gate = ApprovalGate(tmp_path, "ask_first")
    registry = SimpleNamespace(
        lookup_tool=lambda name: caps.get(name),
        lookup_tool_provider=lambda name: provider if name in caps else None,
        get_provider=lambda name: SimpleNamespace(gate=gate) if name == "approval" else None,
    )
    provider.tool_registry = registry
    result = asyncio.run(run_gated_tool(registry, gate, "revit_api_lookup", {"query": "Wall.Flip", "mode": "signature"}))
    assert result["status"] == "ok" and result["lines"][0].startswith("Wall.Flip()")
