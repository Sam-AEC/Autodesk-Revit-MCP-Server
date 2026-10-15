"""Regression tests: heavy imports stay lazy and the bridge client is reused."""

from __future__ import annotations

import subprocess
import sys

import httpx

from revit_mcp_server.bridge import client as client_module
from revit_mcp_server.bridge.client import BridgeClient

HEAVY = ("specklepy", "ifcopenshell", "networkx")


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_importing_mcp_server_does_not_pull_heavy_modules():
    code = (
        "import sys, revit_mcp_server.mcp_server\n"
        f"heavy = [m for m in {HEAVY!r} if m in sys.modules]\n"
        "print(','.join(heavy))\n"
        "sys.exit(1 if heavy else 0)\n"
    )
    result = _run(code)
    assert result.returncode == 0, f"heavy modules imported at startup: {result.stdout.strip()} {result.stderr[-500:]}"


def test_importing_provider_package_does_not_pull_heavy_modules():
    code = (
        "import sys, revit_mcp_server.providers\n"
        "import revit_mcp_server.providers.cloud, revit_mcp_server.providers.ifc\n"
        "import revit_mcp_server.providers.graph, revit_mcp_server.providers.semantic_provider\n"
        "import revit_mcp_server.providers.identity_mapper\n"
        "from revit_mcp_server.providers.graph import SemanticGraphProvider\n"
        "SemanticGraphProvider().get_capabilities()\n"
        f"heavy = [m for m in {HEAVY!r} if m in sys.modules]\n"
        "print(','.join(heavy))\n"
        "sys.exit(1 if heavy else 0)\n"
    )
    result = _run(code)
    assert result.returncode == 0, f"heavy modules imported by providers: {result.stdout.strip()} {result.stderr[-500:]}"


def _patched_bridge(monkeypatch, token=None):
    created: list[httpx.Client] = []
    real_init = httpx.Client.__init__
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"ok": True, "data": {"seen": request.headers.get("authorization")}}
        )
    )

    class Counting(httpx.Client):
        def __init__(self, *args, **kwargs):
            real_init(self, *args, transport=transport, **kwargs)
            created.append(self)

    monkeypatch.setattr(client_module.httpx, "Client", Counting)
    return BridgeClient("http://bridge.test", token=token), created


def test_client_is_reused_across_calls(monkeypatch):
    bridge, created = _patched_bridge(monkeypatch, token="t1")
    for _ in range(5):
        assert bridge.call_tool("x", {})["seen"] == "Bearer t1"
    assert len(created) == 1
    bridge.close()


def test_client_rebuilt_when_token_changes_and_closed_on_close(monkeypatch):
    bridge, created = _patched_bridge(monkeypatch, token="t1")
    bridge.call_tool("x", {})
    bridge.token = "t2"
    assert bridge.call_tool("x", {})["seen"] == "Bearer t2"
    assert len(created) == 2
    assert created[0].is_closed
    bridge.close()
    assert created[1].is_closed
    bridge.call_tool("x", {})
    assert len(created) == 3
    bridge.close()
