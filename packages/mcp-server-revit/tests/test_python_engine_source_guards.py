"""Source guards for the add-in's IronPython engine (no Revit needed).

These read the C# and PowerShell sources, so they catch a regression in what ships
but prove nothing about the loaded add-in; scripts/test-ironpython-runtime.ps1 runs
the engine itself against a build.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ADDIN = REPO_ROOT / "packages" / "revit-bridge-addin"
FACTORY = (ADDIN / "src" / "Bridge" / "PythonEngineFactory.cs").read_text(encoding="utf-8")
RUNNER = (ADDIN / "src" / "Bridge" / "PythonScriptRunner.cs").read_text(encoding="utf-8")
COMMANDS = (ADDIN / "src" / "Bridge" / "BridgeCommandFactory.cs").read_text(encoding="utf-8")
CSPROJ = (ADDIN / "RevitBridge.csproj").read_text(encoding="utf-8")
RUNTIME_SCRIPT = (REPO_ROOT / "scripts" / "test-ironpython-runtime.ps1").read_text(encoding="utf-8")


def _package_versions(name: str) -> dict[str, str]:
    """TargetFramework condition -> version for one PackageReference."""
    found = {}
    for match in re.finditer(rf'<PackageReference Include="{re.escape(name)}" Version="([^"]+)" Condition="([^"]+)"', CSPROJ):
        found["net48" if "=='net48'" in match.group(2) and "!=" not in match.group(2) else "other"] = match.group(1)
    return found


def test_stdlib_package_is_referenced_and_matches_ironpython():
    assert _package_versions("IronPython.StdLib") == _package_versions("IronPython")
    assert len(_package_versions("IronPython.StdLib")) == 2


def test_engine_adds_the_lib_folder_next_to_the_dll_to_the_search_path():
    assert "SetSearchPaths" in FACTORY
    assert '"Lib"' in FACTORY
    assert "Assembly.Location" in FACTORY


def test_execute_python_goes_through_the_factory_and_nothing_else_creates_an_engine():
    handler = COMMANDS.split('[BridgeCommand("revit.execute_python"', 1)[1].split("[BridgeCommand(", 1)[0]
    assert "PythonScriptRunner.Run(" in handler
    assert 'TryGetProperty("mode"' in handler
    sources = list((ADDIN / "src").rglob("*.cs"))
    creators = [p.name for p in sources if "Python.CreateEngine()" in p.read_text(encoding="utf-8")]
    assert creators == ["PythonEngineFactory.cs"]


def test_read_mode_backstops_and_progress_helper_are_present():
    assert 'scope.SetVariable("progress"' in RUNNER
    assert "DocumentChanged +=" in RUNNER and "DocumentChanged -=" in RUNNER
    assert "e.Cancel()" in RUNNER
    assert "read_mode_violation" in RUNNER
    assert "class ProgressBuffer" in RUNNER
    assert "PythonEngineFactory.Create()" in RUNNER


def test_engine_factory_stays_free_of_revit_references():
    # scripts/test-ironpython-runtime.ps1 compiles this one file outside Revit.
    assert "Autodesk.Revit" not in FACTORY


def test_runtime_script_compiles_the_factory_and_checks_the_bundled_modules():
    assert "PythonEngineFactory.cs" in RUNTIME_SCRIPT
    assert "Lib/json/__init__.py" in RUNTIME_SCRIPT
    assert "throw" in RUNTIME_SCRIPT
