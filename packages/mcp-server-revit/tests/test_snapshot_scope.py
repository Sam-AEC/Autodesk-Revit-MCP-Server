"""snapshot_take passes its scope to the add-in and reports a partial capture instead of hiding it."""
import asyncio
import json
from types import SimpleNamespace

from revit_mcp_server.providers.semantic_provider import SemanticProvider
from revit_mcp_server.security.workspace import WorkspaceMonitor


class FakeRevit:
    def __init__(self, path):
        self.path = path
        self.calls = []

    async def execute_tool(self, name, payload):
        self.calls.append((name, payload))
        return {"snapshot_id": "snap1", "path": str(self.path)}


def _write_snapshot(path, truncated):
    path.write_text(json.dumps({
        "schema": "amb.snapshot/1", "snapshot_id": "snap1", "elements": [],
        "counts": {"truncated": truncated, "candidates": 90000, "captured": 5000},
    }), encoding="utf-8")


def _run(tmp_path, monkeypatch, truncated, arguments):
    monkeypatch.setattr("revit_mcp_server.config.config.mode", SimpleNamespace(value="bridge", __eq__=lambda a, b: False), raising=False)
    ws = WorkspaceMonitor([tmp_path])
    src = tmp_path / "snap1.json"
    _write_snapshot(src, truncated)
    revit = FakeRevit(src)
    registry = SimpleNamespace(get_provider=lambda name: revit if name == "revit" else None)
    provider = SemanticProvider(ws, registry)
    result = asyncio.run(provider._snapshot_take(arguments))
    return revit, result


def test_scope_is_sent_to_the_addin(tmp_path, monkeypatch):
    revit, _ = _run(tmp_path, monkeypatch, False, {"categories": ["Doors", "Rooms"], "max_elements": 200, "ignored": 1})
    assert revit.calls == [("revit_extract_snapshot", {"categories": ["Doors", "Rooms"], "max_elements": 200})]


def test_partial_capture_is_reported(tmp_path, monkeypatch):
    _, result = _run(tmp_path, monkeypatch, True, {})
    assert result["truncated"] is True and result["candidates"] == 90000
    assert "categories" in result["note"] and "whole model" in result["note"]


def test_complete_capture_has_no_warning(tmp_path, monkeypatch):
    _, result = _run(tmp_path, monkeypatch, False, {})
    assert result["truncated"] is False and result["note"] is None
