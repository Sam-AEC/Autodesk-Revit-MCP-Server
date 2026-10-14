"""Regressions for LIVE-02/03; HTTP and registry are simulated, never live Revit."""
from __future__ import annotations

import json
import asyncio
import threading
import urllib.error
import urllib.request

import httpx
import pytest

from revit_mcp_server import panel_server
from revit_mcp_server.bridge import discovery
from revit_mcp_server.bridge.client import BridgeClient
from revit_mcp_server.config import BridgeMode
from revit_mcp_server.errors import BridgeError, CommandFailed
from revit_mcp_server.providers.revit import RevitProvider
from revit_mcp_server.security.workspace import WorkspaceMonitor


@pytest.fixture
def panel(tmp_path, monkeypatch):
    monkeypatch.setattr(panel_server.config, "mode", BridgeMode.mock)
    monkeypatch.setenv("MCP_PANEL_TOKEN_FILE", str(tmp_path / "panel.token"))
    server = panel_server.build_server(port=0, workspace=WorkspaceMonitor([tmp_path]))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def post(server, body):
    from revit_mcp_server.security.panel_token import read_token

    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}/execute",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-AMB-Token": read_token()},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as response:
        return response.code, json.loads(response.read())


@pytest.mark.parametrize("script", ["from Autodesk.Revit.DB import Transaction", "doc.Save()", ""])
def test_read_guard_refusal_is_400_and_never_executes_provider(panel, monkeypatch, script):
    executions = []

    async def execute(name, arguments):
        executions.append((name, arguments))
        return {"output": "unexpected"}

    provider = panel.RequestHandlerClass.registry.get_provider("revit")
    monkeypatch.setattr(provider, "execute_tool", execute)
    status, body = post(panel, {
        "tool": "revit_execute_python", "arguments": {"mode": "read", "script": script},
    })
    assert status == 400 and body["ok"] is False and executions == []
    assert "read" in body["error"].lower()


@pytest.mark.parametrize("exception", [ValueError("provider defect"), RuntimeError("provider defect")])
def test_provider_defects_still_return_500(panel, monkeypatch, exception):
    async def execute(name, arguments):
        raise exception

    provider = panel.RequestHandlerClass.registry.get_provider("revit")
    monkeypatch.setattr(provider, "execute_tool", execute)
    status, body = post(panel, {
        "tool": "revit_execute_python", "arguments": {"mode": "read", "script": "print(1)"},
    })
    assert status == 500 and body["ok"] is False and body["error"] == "provider defect"


def switch(**changes):
    fields = dict(
        provider_id="revit", endpoint="http://127.0.0.1:39001", pid=1234,
        host_version="2024", connector_version="1.4.0", protocol_version=2,
        capability_digest="test", session_token="old-token", started_at="2026-10-14T08:00:00Z",
    )
    return discovery.SwitchInfo(**(fields | changes))


def registry_client(monkeypatch):
    original = switch()
    live = [original]
    monkeypatch.setattr(discovery, "discover_switch_list", lambda **kwargs: live)
    client = BridgeClient(original.endpoint, token=original.session_token)
    client.bind_registry_session(original)
    sent = []

    def transport(request):
        sent.append(request)
        if request.url.path == "/tools":
            return httpx.Response(200, json={"tools": ["revit.get_document_info"]})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "healthy"})
        return httpx.Response(200, json={"Status": "ok", "Result": {"document": "Original"}})

    client._http = httpx.Client(transport=httpx.MockTransport(transport))
    client._http_key = (client.token, client.timeout)
    client._sleep = lambda seconds: None
    return client, live, sent


def test_discovered_client_keeps_chosen_session_when_another_revit_opens(monkeypatch):
    client, live, sent = registry_client(monkeypatch)
    live.insert(0, switch(pid=2222, endpoint="http://127.0.0.1:39002", session_token="other-token"))
    try:
        client.initialize()
        assert client.call_tool("revit.get_document_info", {}) == {"document": "Original"}
        assert all(request.url.port == 39001 for request in sent)
    finally:
        client.close()


@pytest.mark.parametrize("replacement", [
    None, switch(pid=2222), switch(started_at="2026-10-14T09:00:00Z"),
    switch(endpoint="http://127.0.0.1:39002"), switch(session_token="replacement-token"),
    switch(host_version="2026"),
])
def test_closed_or_changed_session_refuses_without_redirect_or_request(monkeypatch, replacement):
    client, live, sent = registry_client(monkeypatch)
    live[:] = [] if replacement is None else [replacement]
    try:
        with pytest.raises(BridgeError, match="Reconnect or restart this MCP client"):
            client.call_tool("revit.set_parameter_value", {"value": "write"})
        with pytest.raises(BridgeError, match="changed or closed"):
            client.get_result("earlier-request", wait_s=0)
        assert sent == [] and client.base_url == "http://127.0.0.1:39001" and client.token == "old-token"
    finally:
        client.close()


def test_session_change_between_retry_attempts_does_not_replay_into_replacement(monkeypatch):
    client, live, sent = registry_client(monkeypatch)

    def lost_response(path, body):
        sent.append(body)
        live[:] = [switch(pid=2222, endpoint="http://127.0.0.1:39002")]
        raise httpx.ReadError("original response lost")

    client._post = lost_response
    try:
        # Exercise the real pre-send guard on the second attempt after a lost response.
        def pause(seconds):
            client._post = lambda path, body: BridgeClient._post(client, path, body)

        client._sleep = pause
        with pytest.raises(BridgeError, match="changed or closed"):
            client.call_tool("revit.set_parameter_value", {})
        assert len(sent) == 1
    finally:
        client.close()


def test_provider_binds_discovery_but_explicit_url_stays_pinned(tmp_path, monkeypatch):
    client, live, sent = registry_client(monkeypatch)
    monkeypatch.setattr(discovery, "select_switch", lambda *args, **kwargs: live[0])
    client._registry_session = None
    workspace = WorkspaceMonitor([tmp_path])
    discovered = RevitProvider(workspace, BridgeMode.bridge, bridge_url=None, bridge_factory=lambda *args: client)
    assert discovered._bridge._registry_session is not None

    explicit = BridgeClient("http://127.0.0.1:39001", token="explicit-token")
    explicit._get = lambda path: {"status": "healthy", "tools": []}
    try:
        provider = RevitProvider(workspace, BridgeMode.bridge, bridge_url=explicit.base_url, bridge_factory=lambda *args: explicit)
        assert provider._bridge._registry_session is None
        live.clear()
        explicit._check_registry_session()  # Registry changes must not redirect an explicit URL.
    finally:
        explicit.close()
        client.close()


def rollback_payload():
    return {
        "ok": False, "success": False, "kind": "rolled_back", "message": "Cannot join elements",
        "transaction_status": "RolledBack", "rolled_back": True, "failed_element_ids": [41, 42],
        "element_ids": [41, 42], "revit_messages": [{"severity": "Error", "message": "Cannot join elements",
            "failure_id": "failure-guid", "element_ids": [41], "additional_element_ids": [42]}],
        "warnings": [{"severity": "Warning", "message": "Overlap", "element_ids": [41]}],
        "api_key": "must-not-leak", "output_path": "C:/private/model.rvt",
    }


@pytest.mark.parametrize("envelope", ["native", "blueprint"])
def test_native_error_keeps_structured_revit_failure_and_raises(envelope):
    payload = rollback_payload()
    response = {"Status": "error", "Message": "Revit rejected write", "Result": payload}
    if envelope == "blueprint":
        response = {"ok": False, "message": "Revit rejected write", "data": payload}
    with pytest.raises(CommandFailed, match="Revit rejected write") as failure:
        BridgeClient()._unwrap(response)
    assert failure.value.payload == payload


def test_panel_and_mcp_keep_rollback_details_as_redacted_failures(panel, monkeypatch):
    from revit_mcp_server import mcp_server

    payload = rollback_payload()

    async def execute(name, arguments):
        raise CommandFailed("Revit rejected write", payload=payload)

    registry = panel.RequestHandlerClass.registry
    provider = registry.get_provider("revit")
    monkeypatch.setattr(provider, "execute_tool", execute)
    arguments = {"mode": "read", "script": "print(1)"}
    status, body = post(panel, {"tool": "revit_execute_python", "arguments": arguments})
    assert status == 409 and body["ok"] is False

    monkeypatch.setattr(mcp_server, "registry", registry)
    monkeypatch.setattr(mcp_server, "approval_provider", panel.RequestHandlerClass.approval_provider)
    response = asyncio.run(mcp_server.call_tool("revit_execute_python", arguments))
    assert response.isError is True and response.structuredContent["ok"] is False
    assert response.structuredContent["error"]["kind"] == "bridge_error"
    for result in (body["result"], response.structuredContent["result"]):
        assert result["ok"] is False and result["success"] is False and result["kind"] == "rolled_back"
        assert result["failed_element_ids"] == [41, 42] and result["rolled_back"] is True
        assert result["transaction_status"] == "RolledBack"
        assert result["revit_messages"][0]["additional_element_ids"] == [42]
        assert result["warnings"][0]["message"] == "Overlap"
        assert result["api_key"] == "<redacted>" and result["output_path"] == "<redacted-path>"
    text = response.content[0].text
    assert "failed_element_ids" in text and "must-not-leak" not in text and "C:/private" not in text
