from __future__ import annotations

import httpx


class BridgeClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def send_tool(self, tool_name: str, payload: dict) -> dict:
        response = self.client.post("/tools", json={"tool": tool_name, "payload": payload})
        response.raise_for_status()
        return response.json()
