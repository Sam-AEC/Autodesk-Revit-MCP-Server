from __future__ import annotations

import httpx
import os
import threading
import time
import uuid
from typing import Any

from ..errors import BridgeError, CommandFailed

DEFAULT_SOFT_WAIT_SECONDS = 25.0
# Poll gaps after the add-in's own wait: 0.5 s, 1 s, 2 s, then 3 s until the soft wait ends.
_POLL_BACKOFF = (0.5, 1.0, 2.0, 3.0)
_MAX_POLL_FAILURES = 3


def _soft_wait_from_env() -> float:
    try:
        value = float(os.environ.get("AEC_BRIDGE_SOFT_WAIT_SECONDS", DEFAULT_SOFT_WAIT_SECONDS))
    except ValueError:
        return DEFAULT_SOFT_WAIT_SECONDS
    return value if value > 0 else DEFAULT_SOFT_WAIT_SECONDS


class BridgeClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:3000",
        timeout: int = 30,
        token: str | None = None,
        soft_wait: float | None = None,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.token = token
        # How long one call waits for Revit before it hands back {"status": "running", "request_id": ...}.
        self.soft_wait = soft_wait if soft_wait and soft_wait > 0 else _soft_wait_from_env()
        self._sleep = time.sleep
        self._clock = time.monotonic
        self._tool_catalog: list[str] | None = None
        self._http: httpx.Client | None = None
        self._http_key: tuple[Any, ...] | None = None
        self._http_lock = threading.Lock()
        self._registry_session = None

    def bind_registry_session(self, switch: Any) -> None:
        """Pin an auto-discovered client to the chosen session, never to another Revit."""
        self._registry_session = (
            switch.pid, switch.host_version, switch.started_at,
            switch.endpoint.rstrip('/'), switch.session_token,
        )

    def _check_registry_session(self) -> None:
        if self._registry_session is None:
            return  # Explicit URLs and legacy ports do not use registry discovery.
        from .discovery import discover_switch_list

        pid, year, started_at, endpoint, token = self._registry_session
        for switch in discover_switch_list(prune=False):
            if (switch.provider_id == "revit" and switch.pid == pid
                    and switch.host_version == year and switch.started_at == started_at
                    and switch.endpoint.rstrip('/') == endpoint and switch.session_token == token):
                return
        raise BridgeError(
            f"The selected Revit {year} session (process {pid}) changed or closed. "
            "Reconnect or restart this MCP client to select the current session. "
            "No request was sent to a replacement Revit. Check the model before repeating an earlier write."
        )

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

    def call_tool(self, tool: str, payload: dict[str, Any], wait_s: float | None = None) -> dict[str, Any]:
        """Execute a tool with retry logic.

        A call that outlives the soft wait is not an error: the add-in keeps running it and keeps the
        result, so this returns {"status": "running", "request_id": ...}; pass that id to get_result().
        wait_s overrides the soft wait for this one call (a quick probe should not hold for 25 s).
        """
        self._check_registry_session()
        if self._tool_catalog and tool not in self._tool_catalog:
            raise BridgeError(
                f"Tool '{tool}' not available in bridge. "
                f"Available tools: {', '.join(self._tool_catalog)}"
            )

        request_id = str(uuid.uuid4())
        soft_wait = self.soft_wait if wait_s is None else max(0.5, float(wait_s))
        deadline = self._clock() + soft_wait
        # The add-in answers within wait_ms; keep that below the HTTP timeout so a slow command
        # comes back as "running" instead of as a client-side read timeout.
        wait_ms = int(max(0.5, min(soft_wait, self.timeout - 5)) * 1000)
        last_error = None

        for attempt in range(3):
            try:
                response = self._post(
                    "/execute",
                    {"tool": tool, "payload": payload, "request_id": request_id, "wait_ms": wait_ms}
                )
                if self._is_running(response):
                    return self._await_result(request_id, deadline, first=response)
                return self._unwrap(response)

            except httpx.RequestError as e:
                last_error = e
                if attempt < 2:
                    delay = 2 ** attempt  # 1s, 2s
                    self._sleep(delay)
                    continue
                raise BridgeError(
                    f"Bridge request failed after 3 attempts: {e}"
                ) from e

        raise BridgeError(f"Bridge request failed: {last_error}") from last_error

    def get_result(self, request_id: str, wait_s: float | None = None) -> dict[str, Any]:
        """Collect the outcome of an earlier call by request id.

        Returns the command result when it is done and raises BridgeError when it failed or the id
        is unknown or expired. If it is still going after wait_s (default: the soft wait) it returns
        {"status": "running", "request_id": ...} so the caller can ask again.
        """
        wait = self.soft_wait if wait_s is None else max(0.0, float(wait_s))
        return self._await_result(request_id, self._clock() + wait)

    @staticmethod
    def _is_running(response: dict[str, Any]) -> bool:
        return (response.get("status") or response.get("Status")) in ("running", "queued")

    def _await_result(
        self, request_id: str, deadline: float, first: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        snapshot = first
        polls = 0
        failures = 0
        while True:
            if snapshot is None:
                try:
                    snapshot = self._get(f"/result/{request_id}")
                    failures = 0
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        raise BridgeError(
                            f"Request {request_id} is unknown to the add-in: its result expired "
                            "or Revit was restarted. Check the model before repeating a write."
                        ) from e
                    raise
                except httpx.RequestError as e:
                    failures += 1
                    if failures >= _MAX_POLL_FAILURES:
                        raise BridgeError(
                            f"Lost contact with the bridge while waiting for request {request_id}; "
                            f"it may still be running in Revit. Error: {e}"
                        ) from e

            if snapshot is not None:
                state = snapshot.get("state") or snapshot.get("status") or snapshot.get("Status")
                if state in ("done", "failed"):
                    if snapshot.get("response") is None:
                        raise BridgeError(f"Request {request_id} finished but its result is missing")
                    return self._unwrap(snapshot["response"])
                if state not in ("running", "queued"):
                    return self._unwrap(snapshot)

            remaining = deadline - self._clock()
            if remaining <= 0:
                return self._running_result(request_id, snapshot)
            self._sleep(min(_POLL_BACKOFF[min(polls, len(_POLL_BACKOFF) - 1)], remaining))
            polls += 1
            snapshot = None

    @staticmethod
    def _running_result(request_id: str, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        snapshot = snapshot or {}
        state = snapshot.get("state") or "running"
        result: dict[str, Any] = {
            "status": "running",
            "state": state,
            "request_id": request_id,
            "message": (
                "Revit is still working on this request; nothing has been lost. "
                "Call revit_get_result with this request_id to collect the output. "
                "Do not repeat a write until it has finished."
            ),
        }
        for key in ("tool", "elapsed_ms"):
            if key in snapshot:
                result[key] = snapshot[key]
        return result

    def _unwrap(self, response: dict[str, Any]) -> dict[str, Any]:
        # Blueprint §3.2 envelope: { ok, request_id, data, warnings, artifacts, job }
        # Legacy Revit envelope: { Status/status, Tool, Result/result }
        if "ok" in response:
            if not response["ok"]:
                raise CommandFailed(
                    f"Bridge error: {response.get('message', 'Unknown error')}",
                    payload=response.get("data") if isinstance(response.get("data"), dict) else None,
                )
            result = response.get("data") or {}
        else:
            # Handle both lowercase (status) and Pascal case (Status) from C# server
            status = response.get("status") or response.get("Status", "ok")
            if status == "error":
                message = response.get("message") or response.get("Message", "Unknown error")
                stack = response.get("stack_trace") or response.get("StackTrace", "N/A")
                raise CommandFailed(
                    f"Bridge error: {message}\n"
                    f"Stack: {stack}",
                    payload=(response.get("result") or response.get("Result"))
                    if isinstance(response.get("result") or response.get("Result"), dict) else None,
                )
            # Handle both lowercase and Pascal case for Result
            result = response.get("result") or response.get("Result", {})

        # Normalize element ID keys from specific types to generic element_id
        if isinstance(result, dict):
            self._normalize_element_ids(result)

        return result

    def list_commands(self) -> list[dict[str, Any]]:
        """The add-in's command list: [{name, is_mutating, confirmation_required}]."""
        try:
            return list(self._get("/capabilities").get("tools", []))
        except httpx.RequestError as e:
            raise BridgeError(f"Bridge unreachable at {self.base_url}: {e}") from e

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
        self._check_registry_session()
        resp = self._get_client().get(f"{self.base_url}{path}")
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        self._check_registry_session()
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
