from __future__ import annotations

from datetime import datetime


class MockBridge:
    def send_tool(self, tool_name: str, payload: dict) -> dict:
        now = datetime.utcnow().isoformat()
        return {
            "tool": tool_name,
            "mock": True,
            "timestamp": now,
            "payload": payload,
            "result": {"status": "mock-response"},
        }
