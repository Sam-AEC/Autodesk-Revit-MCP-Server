from __future__ import annotations

import io
import json
import sys
from typing import Callable, Dict, Protocol

from .bridge import BridgeClient, MockBridge
from .config import BridgeMode, Config, config
from .security.audit import AuditRecorder
from .security.workspace import WorkspaceMonitor
from .tools import TOOL_HANDLERS


class BridgeTransport(Protocol):
    def send_tool(self, tool_name: str, payload: dict) -> dict:
        ...


class MCPServer:
    def __init__(
        self,
        config: Config | None = None,
        bridge_factory: Callable[[str], BridgeTransport] | None = None,
    ) -> None:
        self.config = config or config
        self.workspace = WorkspaceMonitor(self.config.allowed_directories)
        self.audit = AuditRecorder(self.config.audit_log)
        self.handlers: Dict[str, Callable[[dict, WorkspaceMonitor], dict]] = TOOL_HANDLERS
        self.bridge = self._build_bridge(bridge_factory)

    def _build_bridge(
        self,
        factory: Callable[[str], BridgeTransport] | None,
    ) -> BridgeTransport:
        if self.config.mode == BridgeMode.bridge:
            if not self.config.bridge_url:
                raise ValueError("Bridge mode requires MCP_REVIT_BRIDGE_URL")
            bridge_factory = factory or (lambda url: BridgeClient(url))
            return bridge_factory(self.config.bridge_url)
        return MockBridge()

    def handle_tool(self, tool_name: str, payload: dict) -> dict:
        handler = self.handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool {tool_name}")

        if self.config.mode == BridgeMode.bridge:
            handler(payload, self.workspace)
            response = self.bridge.send_tool(tool_name, payload)
        else:
            response = handler(payload, self.workspace)

        self.audit.record(tool_name, payload.get("request_id", ""), payload, response)
        return response

    def run(
        self,
        *,
        stdin: io.TextIOBase | None = None,
        stdout: io.TextIOBase | None = None,
    ) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        stdout.write("Revit MCP server started. Awaiting JSON requests.\n")
        stdout.flush()

        while line := stdin.readline():
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                tool = request.get("tool")
                payload = request.get("payload", {})
                response = self.handle_tool(tool, payload)
            except Exception as exc:  # noqa: BLE001
                response = {"status": "error", "message": str(exc)}
            stdout.write(json.dumps({"tool": tool, "response": response}) + "\n")
            stdout.flush()


def run_server() -> None:
    server = MCPServer()
    server.run()
