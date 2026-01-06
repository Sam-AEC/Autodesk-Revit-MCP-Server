from pathlib import Path

from revit_mcp_server.security.workspace import WorkspaceMonitor
from revit_mcp_server.tools import TOOL_HANDLERS


def test_all_handlers_registered():
    assert "revit.health" in TOOL_HANDLERS
    assert "revit.export_report" in TOOL_HANDLERS
    assert len(TOOL_HANDLERS) >= 25


def test_export_quantities_uses_workspace(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    handler = TOOL_HANDLERS["revit.export_quantities"]
    payload = {"request_id": "test", "output_path": str(tmp_path / "quantities.json")}
    response = handler(payload, workspace)
    assert response["categories_exported"] == 5
    assert str(tmp_path) in response["output_path"]
