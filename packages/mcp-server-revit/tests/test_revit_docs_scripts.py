"""Execute the real embedded safety functions against rollbackable API stubs."""
from __future__ import annotations

import ast
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from revit_mcp_server.modules.revit_docs.module import SCRIPT_DIR, build_script


def load_functions(script, names, env):
    tree = ast.parse((SCRIPT_DIR / script).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT_DIR / script), "exec"), env)
    return env


class Element:
    def __init__(self, number, owner=None):
        self.Id = number
        self.owner = owner


class Document:
    def __init__(self, elements, cascade):
        self.elements = {e.Id: e for e in elements}
        self.cascade = cascade

    def GetElement(self, number):
        return self.elements.get(number)

    def Delete(self, number):
        ids = self.cascade.get(number, [number])
        for i in ids:
            self.elements.pop(i, None)
        return ids


class SubTransaction:
    def __init__(self, doc):
        self.doc = doc
        self.status = None

    def Start(self):
        self.before = dict(self.doc.elements)
        self.status = "started"

    def Commit(self):
        self.status = "committed"
        return self.status

    def RollBack(self):
        self.doc.elements = self.before
        self.status = "rolled_back"

    def GetStatus(self):
        return self.status

    def Dispose(self):
        assert self.status != "started"


def deletion_env(elements, cascades):
    doc = Document(elements, cascades)
    env = {"doc": doc, "ElementId": int, "eid": lambda e: e.Id if hasattr(e, "Id") else e,
           "read_tag": lambda e: e.owner, "SubTransaction": SubTransaction,
           "TransactionStatus": SimpleNamespace(Started="started", Committed="committed"),
           "owned_elements": lambda kind, tag, key: [e for e in doc.elements.values()
                                                      if e.owner and e.owner[:2] == (tag, key)]}
    load_functions("_write_prelude.ipy", {"delete_owned", "is_view_internal", "StepError"}, env)
    return env


def test_safe_owned_replacement_includes_tagged_children():
    view = Element(1, ("DOC", "view A", "view"))
    child = Element(2, ("DOC", "view A", "viewport"))
    foreign = Element(3)
    env = deletion_env([view, child, foreign], {1: [1, 2]})
    assert env["delete_owned"]([view]) == [1, 2]
    assert set(env["doc"].elements) == {3}


@pytest.mark.parametrize("owner", [None, ("DOC", "another view", "viewport"), ("OTHER", "view A", "annotation")])
def test_cascade_to_foreign_content_rolls_back_every_deletion(owner):
    first = Element(1, ("DOC", "view A", "view"))
    second = Element(2, ("DOC", "view A", "marker"))
    foreign = Element(3, owner)
    env = deletion_env([first, second, foreign], {1: [1], 2: [2, 3]})
    with pytest.raises(env["StepError"], match="foreign dependent") as error:
        env["delete_owned"]([first, second])
    assert error.value.ids == [3]
    assert set(env["doc"].elements) == {1, 2, 3}


class ViewPart(Element):
    """A dependent Revit makes with a view: it exists until Delete runs, like the real parts of a 3D view."""

    def __init__(self, number, owner_view=-1, category=None, name=""):
        Element.__init__(self, number)
        self.OwnerViewId = owner_view
        self.Category = category
        self.Name = name


class OwnedView(Element):
    ViewType = "ThreeD"
    Name = "iso"

    def __init__(self, number, owner, dependents):
        Element.__init__(self, number, owner)
        self.dependents = dependents

    def GetDependentElements(self, _filter):
        return [self.Id] + self.dependents


def test_parts_revit_makes_with_a_view_are_not_foreign_but_a_sheet_placement_is():
    camera = ViewPart(2, category=SimpleNamespace(Id=-10))
    helper = ViewPart(3, owner_view=1)
    on_sheet = ViewPart(4)
    view = OwnedView(1, ("DOC", "iso", "view"), [2, 3])
    env = deletion_env([view, camera, helper, on_sheet], {1: [1, 2, 3]})
    env["BuiltInCategory"] = SimpleNamespace(OST_Cameras=-10)
    assert env["delete_owned"]([view]) == [1, 2, 3]

    view = OwnedView(1, ("DOC", "iso", "view"), [2, 3, 4])
    env = deletion_env([view, camera, helper, on_sheet], {1: [1, 2, 3, 4]})
    env["BuiltInCategory"] = SimpleNamespace(OST_Cameras=-10)
    with pytest.raises(env["StepError"], match="foreign dependent") as error:
        env["delete_owned"]([view])
    assert error.value.ids == [4]


def test_untagged_requested_element_is_refused_before_delete():
    element = Element(1)
    env = deletion_env([element], {})
    with pytest.raises(env["StepError"], match="ownership tag"):
        env["delete_owned"]([element])
    assert 1 in env["doc"].elements


def publish_env():
    class Directory:
        GetFiles = staticmethod(lambda folder, pattern, option: [str(p) for p in Path(folder).rglob("*") if p.is_file()])
        Exists = staticmethod(lambda path: Path(path).is_dir())
        CreateDirectory = staticmethod(lambda path: Path(path).mkdir(parents=True, exist_ok=True))

    def copy(source, destination, overwrite):
        # Match File.Copy's no-overwrite behavior without a check-then-open race.
        with open(destination, "wb" if overwrite else "xb") as target:
            with open(source, "rb") as original:
                shutil.copyfileobj(original, target)

    env = {"Directory": Directory, "File": SimpleNamespace(Exists=lambda p: Path(p).is_file(), Copy=copy),
           "IoPath": SimpleNamespace(Combine=lambda a, b: str(Path(a) / b), GetDirectoryName=lambda p: str(Path(p).parent)),
           "SearchOption": SimpleNamespace(AllDirectories=True)}
    load_functions("_write_prelude.ipy", {"StepError"}, env)
    return load_functions("export.ipy", {"publish_staged"}, env)


@pytest.mark.parametrize("filename", ["A101 - Floor Plan.pdf", "model - View 1.dwg", "model - View 1.pcp", "refs/view.dwg"])
def test_actual_split_names_and_sidecars_cannot_overwrite(tmp_path, filename):
    stage, target = tmp_path / "stage", tmp_path / "target"
    for root in (stage, target):
        (root / filename).parent.mkdir(parents=True, exist_ok=True)
        (root / filename).write_bytes(b"original" if root == target else b"new")
    (stage / "other.pdf").write_bytes(b"new")
    env = publish_env()
    with pytest.raises(env["StepError"], match="already exists"):
        env["publish_staged"](str(stage), str(target), False)
    assert (target / filename).read_bytes() == b"original"
    assert not (target / "other.pdf").exists()
    published = env["publish_staged"](str(stage), str(target), True)
    assert len(published) == 2
    assert (target / filename).read_bytes() == b"new"


def test_embedded_scripts_compile_and_inputs_are_literals():
    for script in SCRIPT_DIR.glob("*.ipy"):
        compile(script.read_text(encoding="utf-8"), str(script), "exec")
    script = build_script("make_sheet.ipy", {"name": "x'\nraise Exception('oops')", "tag": "DOC"}, write=True)
    compile(script, "built", "exec")


def test_failed_group_assimilation_is_a_failure():
    records = []
    group = SimpleNamespace(Assimilate=lambda: "rolled_back")
    env = {"TransactionStatus": SimpleNamespace(Committed="committed", RolledBack="rolled_back"),
           "meta": lambda *args: records.append(args), "fail": lambda *args: records.append(args), "info": lambda *args: None}
    load_functions("_write_prelude.ipy", {"Runner", "StepError"}, env)
    runner = object.__new__(env["Runner"])
    runner.closed = runner.crashed = False
    runner.failed_steps = runner.failed_ids = runner.warnings = []
    runner.changed = [12]
    runner.post_failed = 0
    runner.on_error = "abort"
    runner.group = group
    runner.outcome = "ok"
    runner.close()
    assert runner.outcome == "group_close_failed"
    assert any(r[0] == "GROUP_CLOSE_FAILED" for r in records)


def test_make_view_crops_a_3d_view_to_its_scope():
    # Live: without a crop the export fits the whole model and a small scope is a few pixels on a blank page.
    source = (SCRIPT_DIR / "make_view.ipy").read_text(encoding="utf-8")
    assert "def frame_3d(view, lo, hi)" in source
    assert "    frame_3d(view, lo, hi)\n" in source
    assert "crop_frames_scope" in source
