"""Direct mode: revit_raw_command sends a native add-in command straight to the bridge, under the same
approval rules as the other escape hatch (revit_execute_python)."""
import asyncio

import pytest

from revit_mcp_server.config import BridgeMode
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.providers.revit import RevitProvider
from revit_mcp_server.security import approval_override as ov
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.workspace import WorkspaceMonitor


class Recorder:
    def __init__(self, *_a, **_k):
        self.calls = []

    def send_tool(self, tool, payload):
        self.calls.append((tool, payload))
        return {"ok": True, "tool": tool}


class _Registry:
    """Just enough registry for run_gated_tool."""

    def __init__(self, provider):
        self.provider = provider
        self.tools = {t.name: t for t in provider.get_capabilities()}

    def lookup_tool_provider(self, name):
        return self.provider if name in self.tools else None

    def lookup_tool(self, name):
        return self.tools.get(name)


def _provider(tmp_path):
    rec = Recorder()
    prov = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.bridge,
                         bridge_url="http://127.0.0.1:1", bridge_factory=lambda url, token=None: rec)
    return prov, rec


def test_it_is_a_mutating_destructive_tool(tmp_path):
    prov, _ = _provider(tmp_path)
    tool = {t.name: t for t in prov.get_capabilities()}["revit_raw_command"]
    assert tool.is_mutating and tool.destructive


def test_native_payload_goes_to_the_named_command_untouched(tmp_path):
    prov, rec = _provider(tmp_path)
    payload = {"start_point": {"x": 0, "y": 0, "z": 0}, "end_point": {"x": 9, "y": 0, "z": 0},
               "height": 10, "level": "L1", "wall_type": "Generic - 200mm"}
    asyncio.run(prov.execute_tool("revit_raw_command", {"command": "revit.create_wall", "payload": payload}))
    assert rec.calls == [("revit.create_wall", payload)]  # wall_type survives: the curated wrapper drops it


@pytest.mark.parametrize("bad", ["", "create_wall", "revit.", "revit.x y", "rhino.draw", "revit.Create", "../revit.x", "revit.a;b"])
def test_only_revit_commands_by_a_plain_name(tmp_path, bad):
    prov, rec = _provider(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(prov.execute_tool("revit_raw_command", {"command": bad, "payload": {}}))
    assert rec.calls == []


def test_not_available_in_mock_mode(tmp_path):
    prov = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    with pytest.raises(ValueError):
        asyncio.run(prov.execute_tool("revit_raw_command", {"command": "revit.list_levels", "payload": {}}))


def _run(tmp_path, mode, window=False):
    prov, rec = _provider(tmp_path)
    gate = ApprovalGate(tmp_path / "ws", mode)
    gate.override_token = "A" * 43
    if window:
        ov.enable_auto(gate.workspace_dir, 10, token="A" * 43)
    args = {"command": "revit.list_levels", "payload": {}}
    return rec, lambda: asyncio.run(run_gated_tool(_Registry(prov), gate, "revit_raw_command", args))


def test_look_only_refuses(tmp_path):
    rec, call = _run(tmp_path, "look_only")
    with pytest.raises(BridgeError):
        call()
    assert rec.calls == []


def test_ask_first_refuses_without_an_approved_plan(tmp_path):
    rec, call = _run(tmp_path, "ask_first")
    with pytest.raises(BridgeError):
        call()
    assert rec.calls == []


def test_auto_window_runs_it_with_no_plan(tmp_path):
    rec, call = _run(tmp_path, "ask_first", window=True)
    call()
    assert rec.calls == [("revit.list_levels", {})]


# ---- discovery for agents: revit_list_commands ----

class _ListingBridge(Recorder):
    def list_commands(self):
        return [{"name": "revit.create_wall", "is_mutating": True}, {"name": "revit.list_levels", "is_mutating": False},
                {"name": "revit.create_floor", "is_mutating": True}]


def _listing_provider(tmp_path):
    return RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.bridge, bridge_url="http://127.0.0.1:1",
                         bridge_factory=lambda url, token=None: _ListingBridge())


def test_list_commands_is_read_only_and_filterable(tmp_path):
    prov = _listing_provider(tmp_path)
    tool = {t.name: t for t in prov.get_capabilities()}["revit_list_commands"]
    assert not tool.is_mutating and not tool.destructive
    everything = asyncio.run(prov.execute_tool("revit_list_commands", {}))
    assert everything["count"] == 3 and everything["commands"][0] == {"command": "revit.create_floor", "mutating": True}
    walls = asyncio.run(prov.execute_tool("revit_list_commands", {"contains": "WALL"}))
    assert [c["command"] for c in walls["commands"]] == ["revit.create_wall"]
    reads = asyncio.run(prov.execute_tool("revit_list_commands", {"mutating": False}))
    assert [c["command"] for c in reads["commands"]] == ["revit.list_levels"]


def test_list_commands_needs_a_live_add_in(tmp_path):
    prov = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    with pytest.raises(ValueError):
        asyncio.run(prov.execute_tool("revit_list_commands", {}))


def test_god_level_tools_tell_an_agent_what_it_needs_to_know(tmp_path):
    tools = {t.name: t for t in RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock).get_capabilities()}
    py = tools["revit_execute_python"].description
    for must in ("doc", "uidoc", "Transaction", "feet", "print(", "revit_list_commands"):
        assert must in py, must
    assert "obj_N" in tools["revit_invoke_method"].description and "use_transaction" in tools["revit_invoke_method"].description
    assert "revit_list_commands" in tools["revit_raw_command"].description or "revit_list_commands" in py
