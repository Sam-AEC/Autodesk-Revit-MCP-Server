from pathlib import Path

from revit_mcp_server.config import BridgeMode, Config
from revit_mcp_server.server import MCPServer


class DummyBridge:
    def __init__(self, url: str) -> None:  # pylint: disable=unused-argument
        self.calls: list[tuple[str, dict]] = []

    def send_tool(self, tool_name: str, payload: dict) -> dict:
        self.calls.append((tool_name, payload))
        return {"echo": tool_name, "payload": payload}


def create_config(tmp_path: Path, **overrides) -> Config:
    return Config(
        workspace_dir=tmp_path,
        allowed_directories=[tmp_path],
        bridge_url=overrides.get("bridge_url"),
        mode=overrides.get("mode", BridgeMode.mock),
    )


def test_handle_tool_with_mock(tmp_path: Path):
    cfg = create_config(tmp_path)
    server = MCPServer(config_obj=cfg)
    response = server.handle_tool("revit.health", {"request_id": "req-1"})
    assert response["status"] == "healthy"


def test_handle_tool_bridge_mode(tmp_path: Path):
    cfg = create_config(tmp_path, bridge_url="http://bridge", mode=BridgeMode.bridge)
    bridge = DummyBridge(cfg.bridge_url)
    server = MCPServer(config_obj=cfg, bridge_factory=lambda _: bridge)
    response = server.handle_tool("revit.health", {"request_id": "req-bridge"})
    assert response["echo"] == "revit.health"
    assert bridge.calls
