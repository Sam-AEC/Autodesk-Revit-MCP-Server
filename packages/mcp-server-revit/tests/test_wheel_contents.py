"""Build the wheel and check that the non-Python data files really ship in it.

Regression guard: module manifests (module.json), QA/QC rules and recipes (yaml)
were once missing from the built wheel, so a ``pip``/``uvx`` install silently lacked
every module tool that a source checkout has. A declaration in pyproject.toml is not
proof; only the built artifact is.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SRC_PACKAGE = PACKAGE_ROOT / "src" / "revit_mcp_server"

pytestmark = pytest.mark.timeout(300)


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if importlib.util.find_spec("build") is None:
        pytest.skip("the 'build' package is not installed (pip install build)")

    # Build from a copy so the source tree never gains build/, dist/ or *.egg-info.
    work = tmp_path_factory.mktemp("wheel-src")
    source = work / "pkg"
    shutil.copytree(
        PACKAGE_ROOT,
        source,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "build", "dist", "*.egg-info", ".pytest_cache", ".venv", "tests"
        ),
    )
    outdir = work / "dist"

    command = [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir), str(source)]
    # Offline and fast when the build backend is already present; otherwise let
    # `build` create its usual isolated environment.
    if importlib.util.find_spec("setuptools") and importlib.util.find_spec("wheel"):
        command.insert(-1, "--no-isolation")
    proc = subprocess.run(command, capture_output=True, text=True, timeout=280)
    assert proc.returncode == 0, f"wheel build failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"

    wheels = sorted(outdir.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def _expected_data_files() -> set[str]:
    expected: set[str] = set()
    for path in (SRC_PACKAGE / "modules").rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(SRC_PACKAGE.parent).as_posix()
        if (
            path.name == "module.json"
            or (path.suffix == ".yaml" and path.parent.name in {"rules", "recipes"})
            or (path.suffix == ".ipy" and path.parent.name == "scripts")
        ):
            expected.add(relative)
    return expected


def test_wheel_contains_module_manifests_rules_and_recipes(built_wheel: Path) -> None:
    expected = _expected_data_files()
    assert any(p.endswith("/module.json") for p in expected), "no module.json found in the source tree"
    assert any("/rules/" in p for p in expected), "no QA/QC rules found in the source tree"
    assert any("/recipes/" in p for p in expected), "no recipes found in the source tree"
    assert any(p.endswith(".ipy") for p in expected), "no embedded IronPython scripts found in the source tree"

    with zipfile.ZipFile(built_wheel) as wheel:
        shipped = set(wheel.namelist())

    missing = sorted(expected - shipped)
    assert not missing, f"data files missing from {built_wheel.name}: {missing}"


def test_wheel_metadata_keeps_mcp_capped_below_2(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as wheel:
        metadata_name = next(n for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))
        metadata = wheel.read(metadata_name).decode("utf-8")
    requires = [
        line.split(":", 1)[1].strip().replace(" ", "")
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist:")
    ]
    assert any(r.startswith("mcp") and "<2" in r for r in requires), requires
    assert any(r.startswith("anthropic") for r in requires), requires
