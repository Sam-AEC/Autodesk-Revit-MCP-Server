"""revit_get_context and revit_get_result: read-only session tools (upgrade plan items 0.1 and 0.4)."""
from __future__ import annotations

import asyncio

import pytest

from revit_mcp_server.config import BridgeMode
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.providers import RevitProvider
from revit_mcp_server.security.workspace import WorkspaceMonitor
from revit_mcp_server.tool_metadata import enrich_tool

CONTEXT = {
    "addin": {"version": "1.4.0", "informational_version": "1.4.0", "module_id": "abc", "assembly_file_time_utc": "2026-10-14T08:00:00Z"},
    "revit": {"version": "2024", "name": "Autodesk Revit 2024", "build": "24.3.0.0", "username": "sam"},
    "document": {
        "title": "Villa", "path": "C:/m/Villa.rvt", "guid": "g-1", "is_family": False, "is_modified": True,
        "is_workshared": False, "central_path": None, "active_view": {"id": 311, "name": "Level 1", "type": "FloorPlan"},
    },
    "queue": {"depth": 0, "retained_results": 2, "result_ttl_seconds": 900},
}
HEALTH = {
    "status": "healthy", "version": "1.4.0.0", "revit_version": "2024", "active_document": "Villa",
    "queue_depth": 1, "retained_results": 2, "running": None,
}


class FakeBridge:
    def __init__(self, command=None, health=None, error=None):
        self.command, self.health, self.error = command, health if health is not None else HEALTH, error
        self.calls = []
        self.results = {}

    def initialize(self):
        pass

    def _get(self, path):
        assert path == "/health"
        return dict(self.health)

    def call_tool(self, tool, payload, wait_s=None):
        self.calls.append((tool, payload, wait_s))
        if self.error:
            raise self.error
        return self.command

    def send_tool(self, tool, payload):
        return self.call_tool(tool, payload)

    def get_result(self, request_id, wait_s=None):
        self.calls.append(("get_result", request_id, wait_s))
        return self.results[request_id]


def provider(tmp_path, bridge, mode=BridgeMode.bridge):
    return RevitProvider(
        workspace=WorkspaceMonitor([tmp_path]), mode=mode,
        bridge_url="http://127.0.0.1:1", bridge_factory=lambda *args: bridge,
    )


def run(prov, name, **args):
    return asyncio.run(prov.execute_tool(name, args))


def test_context_merges_command_and_unqueued_health(tmp_path):
    bridge = FakeBridge(command=dict(CONTEXT))
    result = run(provider(tmp_path, bridge), "revit_get_context")
    assert result["ok"] is True and result["busy"] is False
    assert result["document"]["guid"] == "g-1" and result["document"]["active_view"]["name"] == "Level 1"
    assert result["revit"]["version"] == "2024"
    assert result["queue"]["depth"] == 1 and result["queue"]["running"] is None
    assert result["server"]["approval_mode"] in ("look_only", "ask_first", "auto")
    assert result["addin_supports_context"] is True
    assert bridge.calls == [("revit.get_context", {}, 3.0)], "a quick probe must not hold for the full soft wait"


def test_context_reports_the_running_request_while_revit_is_busy(tmp_path):
    health = dict(HEALTH, running={"request_id": "r1", "tool": "revit.execute_python", "age_ms": 41000})
    bridge = FakeBridge(command={"status": "running", "request_id": "q1"}, health=health)
    result = run(provider(tmp_path, bridge), "revit_get_context")
    assert result["busy"] is True and result["document"] is None
    assert result["queue"]["running"]["age_ms"] == 41000
    assert any("busy" in w for w in result["warnings"])


def test_context_names_a_stale_add_in_instead_of_failing(tmp_path):
    bridge = FakeBridge(error=BridgeError("Tool 'revit.get_context' not available in bridge. Available tools: revit.health"))
    result = run(provider(tmp_path, bridge), "revit_get_context")
    assert result["ok"] is True and result["addin_supports_context"] is False
    assert any("older than this server" in w for w in result["warnings"])
    assert result["addin"]["version"] == "1.4.0.0"


def test_context_flags_a_version_mismatch(tmp_path):
    ctx = dict(CONTEXT, addin={"version": "1.3.0"})
    result = run(provider(tmp_path, FakeBridge(command=ctx)), "revit_get_context")
    server_version = result["server"]["version"]
    if server_version:
        assert any("differ in version" in w for w in result["warnings"])


def test_context_in_mock_mode_is_labelled_mock(tmp_path):
    result = run(provider(tmp_path, FakeBridge(), mode=BridgeMode.mock), "revit_get_context")
    assert result["mock"] is True and "document" not in result


def test_other_bridge_errors_are_not_swallowed(tmp_path):
    bridge = FakeBridge(error=BridgeError("Bridge request failed after 3 attempts"))
    with pytest.raises(BridgeError):
        run(provider(tmp_path, bridge), "revit_get_context")


def test_get_result_passes_the_id_and_wait_to_the_bridge(tmp_path):
    bridge = FakeBridge()
    bridge.results["abc"] = {"output": "done"}
    result = run(provider(tmp_path, bridge), "revit_get_result", request_id=" abc ", wait_s=4)
    assert result == {"output": "done"}
    assert bridge.calls == [("get_result", "abc", 4)]


def test_get_result_needs_an_id_and_a_live_connection(tmp_path):
    prov = provider(tmp_path, FakeBridge())
    with pytest.raises(ValueError, match="request_id"):
        run(prov, "revit_get_result")
    with pytest.raises(ValueError, match="live Revit"):
        run(provider(tmp_path, FakeBridge(), mode=BridgeMode.mock), "revit_get_result", request_id="x")


def test_both_tools_are_listed_read_only_with_no_approval(tmp_path):
    prov = provider(tmp_path, FakeBridge())
    tools = {t.name: t for t in prov.get_capabilities()}
    for name in ("revit_get_context", "revit_get_result"):
        assert name in tools
        assert not tools[name].is_mutating, "read-only tools never go through the approval gate"
        listed = enrich_tool("revit", tools[name])
        assert listed.annotations.readOnlyHint is True
        assert listed.annotations.destructiveHint is False
        assert len(listed.description) >= 40
        for key, prop in listed.inputSchema.get("properties", {}).items():
            assert prop.get("description"), f"{name}.{key} needs a description"


def test_context_reports_the_live_auto_window_not_just_the_configured_mode(tmp_path, monkeypatch):
    from revit_mcp_server.security import approval_override as ov
    from revit_mcp_server.security.approval import ApprovalGate

    monkeypatch.setenv("MCP_PANEL_TOKEN_FILE", str(tmp_path / "panel-hub.token"))
    token = "A" * 43
    gate = ApprovalGate(tmp_path / "ws", "ask_first")
    gate.override_token = token
    prov = provider(tmp_path, FakeBridge(command=dict(CONTEXT)))
    prov.approval_state_source = gate.approval_state

    before = run(prov, "revit_get_context")["server"]
    assert before["approval_mode"] == "ask_first" and before["auto_window"] is None

    window = ov.enable_auto(gate.workspace_dir, 10, token=token)
    live = run(prov, "revit_get_context")["server"]
    assert live["approval_mode"] == "auto"
    assert live["configured_approval_mode"] == "ask_first"
    assert live["auto_expires_at"] == window["expires_at"]
    assert live["auto_window"]["expires_at"] == window["expires_at"]

    ov.disable_auto(gate.workspace_dir)
    assert run(prov, "revit_get_context")["server"]["approval_mode"] == "ask_first"


def test_context_never_shows_auto_over_look_only(tmp_path, monkeypatch):
    from revit_mcp_server.security import approval_override as ov
    from revit_mcp_server.security.approval import ApprovalGate

    monkeypatch.setenv("MCP_PANEL_TOKEN_FILE", str(tmp_path / "panel-hub.token"))
    gate = ApprovalGate(tmp_path / "ws", "look_only")
    gate.override_token = "A" * 43
    ov.enable_auto(gate.workspace_dir, 10, token="A" * 43)
    prov = provider(tmp_path, FakeBridge(command=dict(CONTEXT)))
    prov.approval_state_source = gate.approval_state
    server = run(prov, "revit_get_context")["server"]
    assert server["approval_mode"] == "look_only" and server["auto_expires_at"] is None


def test_registry_wires_the_context_tool_to_the_live_gate(tmp_path, monkeypatch):
    from revit_mcp_server.registry_factory import build_registry
    from revit_mcp_server.security import approval_override as ov

    monkeypatch.setenv("MCP_PANEL_TOKEN_FILE", str(tmp_path / "panel-hub.token"))
    registry, approval, _jobs, _modules, _ws = build_registry(WorkspaceMonitor([tmp_path]))
    gate = approval.gate
    gate.approval_mode, gate.override_token = "ask_first", "A" * 43
    ov.enable_auto(gate.workspace_dir, 5, token="A" * 43)
    context_provider = registry.lookup_tool_provider("revit_get_context")
    server = asyncio.run(context_provider.execute_tool("revit_get_context", {}))["server"]
    assert server["approval_mode"] == "auto"
