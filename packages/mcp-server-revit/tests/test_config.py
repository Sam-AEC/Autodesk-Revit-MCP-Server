import os
from pathlib import Path

from revit_mcp_server.config import Config


def test_config_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("MCP_REVIT_ALLOWED_DIRECTORIES", str(tmp_path))
    cfg = Config()
    assert cfg.workspace_dir == tmp_path
    assert tmp_path in cfg.allowed_directories
