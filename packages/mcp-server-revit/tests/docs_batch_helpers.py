"""Shared fixtures of the revit_docs documentation batch tests (see test_revit_docs_batch.py)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_docs_stub as ds  # noqa: E402
from revit_mcp_server.modules.revit_docs import module as docs  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402

MM = 304.8


class Bridge:
    """The add-in: runs the script it is handed against the stub world and records the mode."""

    def __init__(self, world: Any) -> None:
        self.world, self.modes = world, []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        assert name == "revit_execute_python"
        self.modes.append(args["mode"])
        if args["mode"] == "read":
            validate_read_script(args["script"])
        return {"success": True, "output": self.world.run(args["script"]), "error": ""}


class Env:
    def __init__(self, scene: ds.Scene, tmp_path: Path) -> None:
        self.s, self.w = scene, scene.w
        self.bridge = Bridge(scene.w)
        self.module = docs.RevitDocsModule()
        self.ws = WorkspaceMonitor([tmp_path])

    def write(self, tool: str, **args: Any) -> Dict[str, Any]:
        return getattr(self.module, tool)(approved_executor=self.bridge, workspace=self.ws, **args)

    def read(self, tool: str, **args: Any) -> Dict[str, Any]:
        return getattr(self.module, tool)(tool_executor=self.bridge, workspace=self.ws, **args)


def make_env(monkeypatch, tmp_path):
    """Body of the ``env`` fixture each test module defines: a stub project and a bridge that runs scripts in it."""
    monkeypatch.setattr(docs, "_server_in_mock_mode", lambda: False)
    with ds.installed_docs(monkeypatch) as scene:
        yield Env(scene, tmp_path)


def plan(env: Env, name: str) -> Any:
    return env.s.plans[name]


def ref(view: Any) -> Dict[str, Any]:
    return {"view_id": view.Id.Value}


def failed(result: Dict[str, Any], kind: str) -> None:
    assert result["ok"] is False and result["kind"] == kind, result


def txn_names(env: Env) -> list:
    return [n for k, n in env.w.txn_log if k == "start"]
