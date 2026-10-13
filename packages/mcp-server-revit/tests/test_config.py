import pytest

from revit_mcp_server.config import Config
from revit_mcp_server.errors import WorkspaceViolation
from revit_mcp_server.registry_factory import build_registry
from revit_mcp_server.security.workspace import WorkspaceMonitor


def test_config_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("MCP_REVIT_ALLOWED_DIRECTORIES", str(tmp_path))
    cfg = Config()
    assert cfg.workspace_dir == tmp_path
    assert tmp_path in cfg.allowed_directories


@pytest.fixture
def zero_config(monkeypatch, tmp_path):
    """No MCP_REVIT_* directory env vars, and a fake home so nothing touches the real one."""
    monkeypatch.delenv("MCP_REVIT_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("MCP_REVIT_ALLOWED_DIRECTORIES", raising=False)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    return tmp_path / "Documents" / "AEC Model Bridge"


def test_defaults_without_env(zero_config):
    cfg = Config()
    assert cfg.workspace_dir == zero_config
    assert cfg.allowed_directories == [zero_config]


def test_defaults_are_not_created_until_needed(zero_config):
    cfg = Config()
    assert not zero_config.exists()  # constructing config has no side effect
    cfg.ensure_workspace()
    assert zero_config.is_dir()
    cfg.ensure_workspace()  # idempotent


def test_build_registry_creates_default_workspace_lazily(zero_config, monkeypatch):
    import revit_mcp_server.registry_factory as rf

    monkeypatch.setattr(rf, "config", Config())
    assert not zero_config.exists()
    workspace = build_registry()[-1]
    assert zero_config.is_dir()
    assert workspace.allowed_directories == [zero_config.resolve()]


def test_explicit_values_win_and_are_not_created(zero_config, monkeypatch, tmp_path):
    ws = tmp_path / "explicit"
    ws.mkdir()
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("MCP_REVIT_ALLOWED_DIRECTORIES", str(ws))
    cfg = Config()
    cfg.ensure_workspace()
    assert cfg.workspace_dir == ws
    assert cfg.allowed_directories == [ws]
    assert not zero_config.exists()


def test_explicit_workspace_only_scopes_allowed_to_it(zero_config, monkeypatch, tmp_path):
    ws = tmp_path / "only_ws"
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(ws))
    cfg = Config()
    assert cfg.allowed_directories == [ws]
    assert not ws.exists()  # constructing config creates nothing
    cfg.ensure_workspace()
    assert ws.is_dir()  # allowed dir was derived from the workspace, so it is created on demand


def test_traversal_still_blocked_with_defaults(zero_config):
    cfg = Config()
    cfg.ensure_workspace()
    monitor = WorkspaceMonitor(cfg.allowed_directories)
    assert cfg.workspace_allowed(zero_config / "plans" / "x.json")
    assert monitor.assert_in_workspace(zero_config / "a.json") == (zero_config / "a.json").resolve()
    for bad in (
        zero_config / ".." / "secret.txt",
        zero_config / ".." / ".." / "etc" / "passwd",
        zero_config.parent / "AEC Model Bridge-evil" / "x",
    ):
        assert not cfg.workspace_allowed(bad)
        with pytest.raises(WorkspaceViolation):
            monitor.assert_in_workspace(bad)


def test_workspace_is_first_allowed_directory(monkeypatch, tmp_path):
    """Modules use allowed_directories[0]; the add-in writes under workspace_dir."""
    other = tmp_path / "other"
    ws = tmp_path / "ws"
    other.mkdir()
    ws.mkdir()
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("MCP_REVIT_ALLOWED_DIRECTORIES", f"{other};{ws}")
    cfg = Config()
    assert cfg.allowed_directories[0] == ws
    assert set(cfg.allowed_directories) == {ws, other}


def test_explicit_allowed_list_is_not_widened(monkeypatch, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("MCP_REVIT_ALLOWED_DIRECTORIES", str(other))
    assert Config().allowed_directories == [other]


def test_addin_workspace_resolver_mirrors_python_default():
    """Static parity check with the C# resolver (not compiled here; UNVERIFIED in Revit)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "packages" / "revit-bridge-addin" / "src" / "Bridge"
    helper = (root / "WorkspaceDirectory.cs").read_text(encoding="utf-8")
    assert '"MCP_REVIT_WORKSPACE_DIR"' in helper
    assert 'Path.Combine(home, "Documents", "AEC Model Bridge")' in helper
    for name in ("BridgeCommandFactory.cs", "PanelHubLauncher.cs", "WorkspaceMonitor.cs"):
        text = (root / name).read_text(encoding="utf-8")
        assert "WorkspaceDirectory." in text
        assert 'GetEnvironmentVariable("MCP_REVIT_WORKSPACE_DIR")' not in text


def test_missing_workspace_folder_is_created_instead_of_failing_import(tmp_path, monkeypatch):
    """Regression: the hub died on import (and logged nothing) when the default workspace did not exist yet."""
    from revit_mcp_server.config import Config

    ws = tmp_path / "Documents" / "AEC Model Bridge"
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("MCP_REVIT_ALLOWED_DIRECTORIES", str(ws))
    cfg = Config()
    assert ws.is_dir() and cfg.allowed_directories == [ws]


def test_other_missing_allowed_directories_still_fail(tmp_path, monkeypatch):
    from pydantic import ValidationError
    from revit_mcp_server.config import Config

    ws = tmp_path / "ws"
    monkeypatch.setenv("MCP_REVIT_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("MCP_REVIT_ALLOWED_DIRECTORIES", f"{ws};{tmp_path / 'elsewhere'}")
    with pytest.raises(ValidationError):
        Config()
