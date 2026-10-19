import pytest

from revit_mcp_server.config import Config


@pytest.mark.parametrize("value", [
    "", "  ", "http://127.0.0.1:3000", "http://127.0.0.1:3000/", "HTTP://localhost:3000",
])
def test_legacy_default_bridge_url_means_not_set(value, monkeypatch):
    monkeypatch.setenv("MCP_REVIT_BRIDGE_URL", value)
    assert Config().bridge_url is None


@pytest.mark.parametrize("value", ["http://127.0.0.1:39001", "http://127.0.0.1:3001"])
def test_other_explicit_bridge_url_stays_pinned(value, monkeypatch):
    monkeypatch.setenv("MCP_REVIT_BRIDGE_URL", value)
    assert Config().bridge_url == value
