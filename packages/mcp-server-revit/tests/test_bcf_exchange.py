"""Tests for the BCF 2.1 export/import module (UNVERIFIED against other BCF tools)."""
import importlib.util
import os
import sqlite3
import stat
import zipfile
from pathlib import Path

import pytest


def _load():
    p = Path(__file__).parent.parent / "src/revit_mcp_server/modules/bcf_exchange/module.py"
    spec = importlib.util.spec_from_file_location("_bcf_impl", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bcf = _load()


class WS:
    def __init__(self, p):
        self.allowed_directories = [p]


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    return WS(root)


@pytest.fixture
def mod():
    return bcf.BcfExchangeModule()


def _zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return path


MARKUP = b'<?xml version="1.0"?><Markup><Topic Guid="g1" TopicStatus="Open"><Title>T</Title></Topic></Markup>'


def test_round_trip(mod, ws):
    issues = [
        {"title": "Door has no mark", "description": "Fix & <check>", "status": "Open", "priority": "High",
         "element_uids": ["abc-uid-1", "2O2Fr$t4X7Zf8NOew3FLOH"], "ifc_guids": ["0DWgwt6o1FOx7466fPk$jl"],
         "author": "sam", "assigned_to": "bob"},
        {"title": "No elements", "description": "plain"},
    ]
    out = mod.export_bcf("issues.bcfzip", issues=issues, workspace=ws)
    assert out["issue_count"] == 2
    res = mod.import_bcf(out["path"], workspace=ws)
    assert res["bcf_version"] == "2.1"
    by_title = {i["title"]: i for i in res["issues"]}
    d = by_title["Door has no mark"]
    assert d["description"] == "Fix & <check>"
    assert d["priority"] == "High" and d["status"] == "Open" and d["assigned_to"] == "bob"
    assert "abc-uid-1" in d["element_uids"]
    assert set(d["ifc_guids"]) == {"0DWgwt6o1FOx7466fPk$jl", "2O2Fr$t4X7Zf8NOew3FLOH"}
    assert by_title["No elements"]["element_uids"] == []


def test_empty_list(mod, ws):
    out = mod.export_bcf("empty.bcfzip", issues=[], workspace=ws)
    assert out["issue_count"] == 0
    res = mod.import_bcf("empty.bcfzip", workspace=ws)
    assert res["issues"] == [] and res["bcf_version"] == "2.1"


def test_qaqc_issues_exported(mod, ws):
    db = ws.allowed_directories[0] / "qaqc_issues.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE issues (id TEXT, doc_guid TEXT, rule_id TEXT, severity TEXT, element_uid TEXT,"
                 " label TEXT, message TEXT, fix_template TEXT, status TEXT, created_at TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO issues VALUES ('i1','d','door_missing_mark','error','uid-9','Door','No mark','', 'open','2026-01-01T00:00:00Z','x')")
    conn.commit()
    conn.close()
    mod.export_bcf("q.bcfzip", use_qaqc_issues=True, workspace=ws)
    res = mod.import_bcf("q.bcfzip", workspace=ws)
    assert res["issue_count"] == 1
    assert res["issues"][0]["priority"] == "High"
    assert res["issues"][0]["element_uids"] == ["uid-9"]


def test_export_no_overwrite_and_extension(mod, ws):
    mod.export_bcf("a.bcfzip", issues=[], workspace=ws)
    with pytest.raises(bcf.BcfError):
        mod.export_bcf("a.bcfzip", issues=[], workspace=ws)
    mod.export_bcf("a.bcfzip", issues=[], overwrite=True, workspace=ws)
    with pytest.raises(bcf.BcfError):
        mod.export_bcf("a.zip", issues=[], workspace=ws)


def test_bad_issue_shape(mod, ws):
    with pytest.raises(bcf.BcfError):
        mod.export_bcf("b.bcfzip", issues=["nope"], workspace=ws)


# --- sandbox ---

def test_sandbox_rejects_outside_paths(mod, ws, tmp_path):
    with pytest.raises(bcf.BcfError):
        mod.export_bcf(str(tmp_path / "outside.bcfzip"), issues=[], workspace=ws)
    with pytest.raises(bcf.BcfError):
        mod.export_bcf("../escape.bcfzip", issues=[], workspace=ws)
    outside = _zip(tmp_path / "o.bcfzip", [("bcf.version", b"<Version VersionId='2.1'/>")])
    with pytest.raises(bcf.BcfError):
        mod.import_bcf(str(outside), workspace=ws)
    assert not (tmp_path / "escape.bcfzip").exists()


def test_sandbox_rejects_symlink_escape(mod, ws, tmp_path):
    target = _zip(tmp_path / "t.bcfzip", [("bcf.version", b"<Version VersionId='2.1'/>")])
    link = ws.allowed_directories[0] / "link.bcfzip"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("link.bcfzip", workspace=ws)


# --- malicious zips ---

@pytest.mark.parametrize("name", ["../evil.txt", "g/../../evil.txt", "/abs/evil.txt", "C:/evil.txt", "a\\b.txt"])
def test_rejects_bad_entry_names(mod, ws, name):
    _zip(ws.allowed_directories[0] / "m.bcfzip", [("g1/markup.bcf", MARKUP), (name, b"x")])
    if name == "a\\b.txt" and os.sep == "\\":
        # On Windows zipfile itself rewrites '\\' to '/' when writing and reading, so the
        # reader only ever sees the harmless relative name 'a/b.txt': nothing to reject.
        assert mod.import_bcf("m.bcfzip", workspace=ws)["issue_count"] == 1
        return
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("m.bcfzip", workspace=ws)


def test_rejects_symlink_entry(mod, ws):
    p = ws.allowed_directories[0] / "s.bcfzip"
    with zipfile.ZipFile(p, "w") as zf:
        info = zipfile.ZipInfo("g1/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("s.bcfzip", workspace=ws)


def test_rejects_zip_bomb_entry(mod, ws):
    big = b"0" * (bcf.MAX_ENTRY_BYTES + 1024)
    _zip(ws.allowed_directories[0] / "b.bcfzip", [("g1/markup.bcf", big)])
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("b.bcfzip", workspace=ws)


def test_rejects_high_ratio(mod, ws):
    data = b"0" * (2 * 1024 * 1024)
    _zip(ws.allowed_directories[0] / "r.bcfzip", [("g1/markup.bcf", data)])
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("r.bcfzip", workspace=ws)


def test_rejects_too_many_entries(mod, ws, monkeypatch):
    monkeypatch.setattr(bcf, "MAX_ENTRIES", 5)
    _zip(ws.allowed_directories[0] / "n.bcfzip", [(f"g{i}/x.txt", b"x") for i in range(6)])
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("n.bcfzip", workspace=ws)


def test_rejects_xxe_and_entity_expansion(mod, ws):
    xxe = (b'<?xml version="1.0"?><!DOCTYPE m [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
           b'<Markup><Topic Guid="g1"><Title>&x;</Title></Topic></Markup>')
    _zip(ws.allowed_directories[0] / "x.bcfzip", [("g1/markup.bcf", xxe)])
    with pytest.raises(bcf.BcfError, match="DOCTYPE"):
        mod.import_bcf("x.bcfzip", workspace=ws)
    lol = (b'<?xml version="1.0"?><!doctype l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
           b'<Markup><Topic Guid="g1"><Title>&b;</Title></Topic></Markup>')
    _zip(ws.allowed_directories[0] / "l.bcfzip", [("g1/markup.bcf", lol)])
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("l.bcfzip", workspace=ws)


def test_rejects_utf16_xml(mod, ws):
    data = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE m [<!ENTITY x "y">]><Markup/>'.encode("utf-16")
    _zip(ws.allowed_directories[0] / "u.bcfzip", [("g1/markup.bcf", data)])
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("u.bcfzip", workspace=ws)


def test_not_a_zip_and_missing(mod, ws):
    (ws.allowed_directories[0] / "junk.bcfzip").write_bytes(b"not a zip")
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("junk.bcfzip", workspace=ws)
    with pytest.raises(bcf.BcfError):
        mod.import_bcf("missing.bcfzip", workspace=ws)


def test_tools_listed_via_registry(tmp_path):
    from revit_mcp_server.config import Config
    from revit_mcp_server.module_registry import ModuleRegistry

    cfg = Config(workspace_dir=tmp_path, allowed_directories=[tmp_path], audit_log=tmp_path / "a.log",
                 enable_user_modules=False)
    reg = ModuleRegistry(config_obj=cfg)
    reg.discover_and_load()
    m = reg.get_module("bcf_exchange")
    assert m is not None and not any(c.is_mutating for c in m.manifest.commands)


# --- BCF 2.1 schema-shape regressions (review findings) ---

def _exported(mod, ws, project_name=""):
    issues = [{"title": "T", "element_uids": ["abc-uid-1", "2O2Fr$t4X7Zf8NOew3FLOH"]}]
    out = mod.export_bcf("s.bcfzip", issues=issues, project_name=project_name, workspace=ws)
    return zipfile.ZipFile(out["path"])


def test_file_attribute_is_isExternal(mod, ws):
    zf = _exported(mod, ws)
    name = next(n for n in zf.namelist() if n.endswith("markup.bcf"))
    data = zf.read(name).decode()
    assert 'isExternal="false"' in data and "IsExternal" not in data


def test_viewpoint_guid_shared_between_markup_and_visinfo(mod, ws):
    import xml.etree.ElementTree as ET
    zf = _exported(mod, ws)
    markup = ET.fromstring(zf.read(next(n for n in zf.namelist() if n.endswith("markup.bcf"))))
    vis = ET.fromstring(zf.read(next(n for n in zf.namelist() if n.endswith(".bcfv"))))
    assert markup.find("Viewpoints").attrib["Guid"] == vis.attrib["Guid"]


def test_components_have_visibility_and_child_originating_system(mod, ws):
    import xml.etree.ElementTree as ET
    zf = _exported(mod, ws)
    vis = ET.fromstring(zf.read(next(n for n in zf.namelist() if n.endswith(".bcfv"))))
    comps = vis.find("Components")
    assert [c.tag for c in comps] == ["Selection", "Visibility"]
    revit = [c for c in comps.find("Selection") if "IfcGuid" not in c.attrib]
    assert revit and all("OriginatingSystem" not in c.attrib for c in revit)
    assert [ch.tag for ch in revit[0]] == ["OriginatingSystem", "AuthoringToolId"]


def test_project_file_has_extension_schema(mod, ws):
    import xml.etree.ElementTree as ET
    zf = _exported(mod, ws, project_name="P")
    proj = ET.fromstring(zf.read("project.bcfp"))
    assert [c.tag for c in proj] == ["Project", "ExtensionSchema"]


def test_topic_directory_entries_present(mod, ws):
    zf = _exported(mod, ws)
    folder = next(n for n in zf.namelist() if n.endswith("markup.bcf")).split("/")[0]
    names = zf.namelist()
    assert f"{folder}/" in names
    assert names.index(f"{folder}/") < names.index(f"{folder}/markup.bcf")


def test_round_trip_still_reads_revit_ids_after_schema_fix(mod, ws):
    _exported(mod, ws)
    res = mod.import_bcf("s.bcfzip", workspace=ws)
    assert res["issues"][0]["element_uids"] == ["abc-uid-1"]


def test_clean_strips_invalid_xml_chars():
    assert bcf._clean("a\x00b\x0bc￾d\x1fe\ud800f") == "abcdef"
    assert bcf._clean("tab\tnl\n ok") == "tab\tnl\n ok"
