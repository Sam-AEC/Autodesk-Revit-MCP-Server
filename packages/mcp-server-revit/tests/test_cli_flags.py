"""--help and --version must print and exit; they must not start the long-running servers."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

import revit_mcp_server


@pytest.mark.parametrize(
    "module", ["revit_mcp_server.mcp_server", "revit_mcp_server.panel_server"]
)
def test_help_exits_without_starting_the_server(module: str, tmp_path) -> None:
    env = {
        **os.environ,
        "MCP_REVIT_MODE": "mock",
        "MCP_REVIT_WORKSPACE_DIR": str(tmp_path),
        "MCP_REVIT_ALLOWED_DIRECTORIES": str(tmp_path),
    }
    out = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True, text=True, env=env, timeout=60, stdin=subprocess.DEVNULL,
    )
    assert out.returncode == 0
    assert "usage:" in out.stdout


def test_version_flag(tmp_path) -> None:
    env = {**os.environ, "MCP_REVIT_MODE": "mock", "MCP_REVIT_WORKSPACE_DIR": str(tmp_path),
           "MCP_REVIT_ALLOWED_DIRECTORIES": str(tmp_path)}
    out = subprocess.run(
        [sys.executable, "-m", "revit_mcp_server.mcp_server", "--version"],
        capture_output=True, text=True, env=env, timeout=60, stdin=subprocess.DEVNULL,
    )
    assert out.returncode == 0
    assert revit_mcp_server.__version__ in out.stdout
