from __future__ import annotations

import httpx
import threading
import time
import uuid
from typing import Any

from ..errors import BridgeError


class BridgeClient:
    def __init__(self, base_url: str = "http://127.0.0.1:3000", timeout: int = 30, token: str | None = None):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.token = token
        self._tool_catalog: list[str] | None = None
        self._http: httpx.Client | None = None
        self._http_key: tuple[Any, ...] | None = None
        self._http_lock = threading.Lock()

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
                f"Ensure Revit is running with the AEC Model Bridge add-in loaded. Error: {e}"
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

                # Blueprint §3.2 envelope: { ok, request_id, data, warnings, artifacts, job }
                # Legacy Revit envelope: { Status/status, Tool, Result/result }
                if "ok" in response:
                    if not response["ok"]:
                        raise BridgeError(
                            f"Bridge error: {response.get('message', 'Unknown error')}"
                        )
                    result = response.get("data") or {}
                else:
                    # Handle both lowercase (status) and Pascal case (Status) from C# server
                    status = response.get("status") or response.get("Status", "ok")
                    if status == "error":
                        message = response.get("message") or response.get("Message", "Unknown error")
                        stack = response.get("stack_trace") or response.get("StackTrace", "N/A")
                        raise BridgeError(
                            f"Bridge error: {message}\n"
                            f"Stack: {stack}"
                        )
                    # Handle both lowercase and Pascal case for Result
                    result = response.get("result") or response.get("Result", {})

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

    def _get_client(self) -> httpx.Client:
        """Return the shared httpx.Client, rebuilding it if the token or timeout changed."""
        key = (self.token, self.timeout)
        with self._http_lock:
            if self._http is None or self._http_key != key:
                old = self._http
                headers = {}
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"
                self._http = httpx.Client(headers=headers, timeout=self.timeout)
                self._http_key = key
                if old is not None:
                    old.close()
            return self._http

    def close(self) -> None:
        """Close the shared HTTP client. A later call transparently rebuilds it."""
        with self._http_lock:
            client, self._http, self._http_key = self._http, None, None
        if client is not None:
            client.close()

    def __enter__(self) -> "BridgeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str) -> dict[str, Any]:
        resp = self._get_client().get(f"{self.base_url}{path}")
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = self._get_client().post(f"{self.base_url}{path}", json=data)
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
