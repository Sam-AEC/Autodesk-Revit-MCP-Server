from __future__ import annotations

import httpx
import time
import uuid
from typing import Any

from ..errors import BridgeError


class BridgeClient:
    def __init__(self, base_url: str = "http://127.0.0.1:3000", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._tool_catalog: list[str] | None = None

    def initialize(self) -> None:
        """Check bridge health and fetch tool catalog on startup."""
        try:
            health = self._get("/health")
            if health.get("status") != "healthy":
                raise BridgeError(f"Bridge unhealthy: {health}")

            tools_resp = self._get("/tools")
            self._tool_catalog = tools_resp.get("tools", [])

        except httpx.RequestError as e:
            raise BridgeError(
                f"Bridge unreachable at {self.base_url}. "
                f"Ensure Revit is running with RevitMCP add-in loaded. Error: {e}"
            ) from e

    def call_tool(self, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool with retry logic."""
        if self._tool_catalog and tool not in self._tool_catalog:
            raise BridgeError(
                f"Tool '{tool}' not available in bridge. "
                f"Available tools: {', '.join(self._tool_catalog)}"
            )

        request_id = str(uuid.uuid4())
        last_error = None

        for attempt in range(3):
            try:
                response = self._post(
                    "/execute",
                    {"tool": tool, "payload": payload, "request_id": request_id}
                )

                if response.get("status") == "error":
                    raise BridgeError(
                        f"Bridge error: {response.get('message')}\n"
                        f"Stack: {response.get('stack_trace', 'N/A')}"
                    )

                result = response.get("result", {})

                # Normalize element ID keys from specific types to generic element_id
                self._normalize_element_ids(result)

                return result

            except httpx.RequestError as e:
                last_error = e
                if attempt < 2:
                    delay = 2 ** attempt  # 1s, 2s
                    time.sleep(delay)
                    continue
                raise BridgeError(
                    f"Bridge request failed after 3 attempts: {e}"
                ) from e

        raise BridgeError(f"Bridge request failed: {last_error}") from last_error

    def send_tool(self, tool_name: str, payload: dict) -> dict:
        """Legacy method for backward compatibility."""
        return self.call_tool(tool_name, payload)

    def _get(self, path: str) -> dict[str, Any]:
        with httpx.Client() as client:
            resp = client.get(f"{self.base_url}{path}", timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client() as client:
            resp = client.post(
                f"{self.base_url}{path}",
                json=data,
                timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()

    def _normalize_element_ids(self, result: dict[str, Any]) -> None:
        """Normalize specific element ID keys to generic element_id for consistency."""
        # Map specific element type IDs to generic element_id
        id_keys = [
            'wall_id', 'floor_id', 'roof_id', 'door_id', 'window_id',
            'column_id', 'beam_id', 'level_id', 'view_id', 'sheet_id',
            'room_id', 'grid_id', 'family_instance_id', 'element_id'
        ]

        for key in id_keys:
            if key in result and 'element_id' not in result:
                result['element_id'] = result[key]
                break
