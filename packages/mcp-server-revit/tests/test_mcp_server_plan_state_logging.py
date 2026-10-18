"""call_tool must log (not swallow) a failed plan-state update after a mutating tool ran."""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from revit_mcp_server import mcp_server


class _Provider:
    async def execute_tool(self, name, arguments):
        return {"ok": True}


class _Registry:
    def lookup_tool_provider(self, name):
        return _Provider()

    def lookup_tool(self, name):
        return SimpleNamespace(is_mutating=True)


class _Gate:
    def check_tool_execution(self, name, arguments):
        return None

    def update_plan_state(self, plan_id, state):
        raise RuntimeError("state store unavailable")


def test_plan_state_failure_is_logged_and_result_unchanged(monkeypatch, caplog):
    monkeypatch.setattr(mcp_server, "registry", _Registry(), raising=False)
    monkeypatch.setattr(
        mcp_server, "approval_provider", SimpleNamespace(gate=_Gate()), raising=False
    )

    with caplog.at_level(logging.ERROR, logger=mcp_server.logger.name):
        result = asyncio.run(mcp_server.call_tool("set_thing", {"plan_id": "plan-123"}))

    assert "set_thing executed successfully" in result[0].text
    records = [r for r in caplog.records if "could not be marked executed" in r.getMessage()]
    assert len(records) == 1
    assert "plan-123" in records[0].getMessage()
    assert "set_thing" in records[0].getMessage()
    assert records[0].exc_info and records[0].exc_info[0] is RuntimeError
