"""Tests for agent_bridge.py's CLI-shelling logic.

None of these invoke a real `claude`/`codex` process — subprocess.run and
shutil.which are monkeypatched so the tests exercise argument construction,
output parsing, and error handling without depending on those CLIs being
installed or authenticated in CI.
"""
from __future__ import annotations

import json
import subprocess

from revit_mcp_server import agent_bridge


def _completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_unknown_provider_returns_error():
    result = agent_bridge.run_agent_turn("gpt-nobody", "hello", None)
    assert result == {"ok": False, "error": "Unknown agent provider 'gpt-nobody' (expected 'claude' or 'codex')"}


def test_claude_missing_cli(monkeypatch):
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: None)
    result = agent_bridge.run_agent_turn("claude", "hello", None)
    assert result["ok"] is False
    assert "claude" in result["error"]


def test_claude_first_turn_uses_session_id_and_returns_response(monkeypatch):
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/claude")

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        payload = json.dumps({"result": "3 doors found on Level 1", "session_id": "abc-123"})
        return _completed(args, stdout=payload)

    monkeypatch.setattr(agent_bridge.subprocess, "run", fake_run)

    result = agent_bridge.run_agent_turn("claude", "how many doors on level 1?", None)

    assert result == {"ok": True, "response": "3 doors found on Level 1", "session_id": "abc-123"}
    assert "--session-id" in captured["args"]
    assert "--resume" not in captured["args"]
    assert "--strict-mcp-config" in captured["args"]
    # Built-in tools must be disabled — chat should only reach Revit via MCP.
    tools_index = captured["args"].index("--tools")
    assert captured["args"][tools_index + 1] == ""


def test_claude_resumes_existing_session(monkeypatch):
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/claude")

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _completed(args, stdout=json.dumps({"result": "ok", "session_id": "abc-123"}))

    monkeypatch.setattr(agent_bridge.subprocess, "run", fake_run)

    result = agent_bridge.run_agent_turn("claude", "and level 2?", "abc-123")

    assert result["session_id"] == "abc-123"
    assert "--resume" in captured["args"]
    resume_index = captured["args"].index("--resume")
    assert captured["args"][resume_index + 1] == "abc-123"


def test_claude_nonzero_exit_returns_error(monkeypatch):
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        agent_bridge.subprocess, "run",
        lambda args, **kwargs: _completed(args, returncode=1, stderr="boom"),
    )

    result = agent_bridge.run_agent_turn("claude", "hi", None)
    assert result == {"ok": False, "error": "boom"}


def test_claude_timeout_returns_error(monkeypatch):
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/claude")

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(agent_bridge.subprocess, "run", fake_run)

    result = agent_bridge.run_agent_turn("claude", "hi", None)
    assert result["ok"] is False
    assert "did not respond" in result["error"]


def test_claude_non_json_stdout_falls_back_to_raw_text(monkeypatch):
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        agent_bridge.subprocess, "run",
        lambda args, **kwargs: _completed(args, stdout="plain text reply\n"),
    )

    result = agent_bridge.run_agent_turn("claude", "hi", None)
    assert result["ok"] is True
    assert result["response"] == "plain text reply"


def test_codex_missing_cli(monkeypatch):
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: None)
    result = agent_bridge.run_agent_turn("codex", "hello", None)
    assert result["ok"] is False
    assert "codex" in result["error"]


def test_codex_message_starting_with_dash_is_not_parsed_as_a_flag(monkeypatch):
    monkeypatch.setattr(agent_bridge, "_CODEX_REGISTRATION_CHECKED", True)
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/codex")

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        out_index = args.index("-o") + 1
        with open(args[out_index], "w", encoding="utf-8") as f:
            f.write("done")
        return _completed(args, stdout="")

    monkeypatch.setattr(agent_bridge.subprocess, "run", fake_run)

    agent_bridge.run_agent_turn("codex", "-fix the wall heights", None)

    args = captured["args"]
    assert "--" in args
    dash_index = args.index("--")
    # everything before "--" must be a recognized flag/value, the message
    # must be the last argument, after "--", so codex's parser can't treat
    # a leading "-" in the message as a flag.
    assert args[dash_index + 1] == "-fix the wall heights"
    assert dash_index + 1 == len(args) - 1


def test_codex_success_reads_last_message_file(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_bridge, "_CODEX_REGISTRATION_CHECKED", True)
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/codex")

    def fake_run(args, **kwargs):
        out_index = args.index("-o") + 1
        with open(args[out_index], "w", encoding="utf-8") as f:
            f.write("42 walls on Level 2")
        return _completed(args, stdout=json.dumps({"session_id": "codex-session-1"}) + "\n")

    monkeypatch.setattr(agent_bridge.subprocess, "run", fake_run)

    result = agent_bridge.run_agent_turn("codex", "how many walls?", None)

    assert result == {"ok": True, "response": "42 walls on Level 2", "session_id": "codex-session-1"}


def test_codex_resume_keeps_session_id_if_not_echoed(monkeypatch):
    monkeypatch.setattr(agent_bridge, "_CODEX_REGISTRATION_CHECKED", True)
    monkeypatch.setattr(agent_bridge.shutil, "which", lambda _name: "/usr/bin/codex")

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        out_index = args.index("-o") + 1
        with open(args[out_index], "w", encoding="utf-8") as f:
            f.write("done")
        return _completed(args, stdout="")

    monkeypatch.setattr(agent_bridge.subprocess, "run", fake_run)

    result = agent_bridge.run_agent_turn("codex", "continue", "codex-session-1")

    assert result["session_id"] == "codex-session-1"
    assert "resume" in captured["args"]


def test_cli_never_runs_in_the_hubs_own_working_directory(monkeypatch, tmp_path):
    """Regression: from the bundled Python folder the CLI's MCP server failed to start (python311.dll
    conflict), so the chat model had zero Revit tools and improvised."""
    import os

    monkeypatch.setattr(agent_bridge.config, "workspace_dir", tmp_path / "ws")
    seen = []

    def fake_run(args, **kwargs):
        seen.append(kwargs.get("cwd"))
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"result": "ok", "session_id": "s"}), stderr="")

    monkeypatch.setattr(agent_bridge.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(agent_bridge.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    agent_bridge.run_agent_turn("claude", "hello", None)
    assert seen and seen[0] == str(tmp_path / "ws") and seen[0] != os.getcwd()
    assert (tmp_path / "ws").is_dir()
