"""Browser tests for the panel chat UI (panel/chat.js) in headless Chromium.

No npm dependencies: the page runs its own small in-page test runner
(tests/panel_web/lib.js) and Chromium's `--dump-dom` prints the JSON results, which
this module turns into one pytest case per browser case. Two pages are exercised:

* the REAL panel/index.html + app.js + chat.js with a stubbed `window.chrome.webview`
  (copied to a temp dir with only the stub and driver scripts injected, so the page's
  Content-Security-Policy is the real one and any inline script/style would be blocked);
* a standalone XSS / control-character page for the markdown renderer.

Skipped cleanly, with the reason, when no Chromium can load a trivial page (set AMB_CHROMIUM
to point at one; AMB_REQUIRE_BROWSER=1 turns that skip into a failure). A page that never
finishes fails within a minute with the browser's stderr instead of hanging.
Anything needing live WebView2 (clipboard permission, CSP on file://, IME, DPI) is NOT
covered here; check it by hand in Revit.
"""

from __future__ import annotations

import glob
import html
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PANEL = ROOT / "panel"
WEB = Path(__file__).resolve().parent / "panel_web"
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
)


def _candidates() -> list[str]:
    """Every Chromium-family binary we can find, most predictable first."""
    found: list[str] = []
    env = os.environ.get("AMB_CHROMIUM")
    if env and Path(env).exists():
        found.append(env)
    bases = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers", str(Path.home() / ".cache/ms-playwright")]
    for base in filter(None, bases):
        for pattern in ("chromium-*/chrome-linux/chrome", "chromium_headless_shell-*/chrome-linux/headless_shell"):
            found += sorted(glob.glob(os.path.join(base, pattern)), reverse=True)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        path = shutil.which(name)
        if path:
            found.append(path)
    return list(dict.fromkeys(found))


# Flags that keep a headless browser self-contained on a CI runner: no sandbox (runners and
# containers forbid user namespaces), no crash reporter or background services that could
# outlive the browser, no first-run or update work.
_FLAGS = [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-crash-reporter",
    "--disable-breakpad",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-extensions",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
]
LAUNCH_TIMEOUT = 60


def _dump_dom(chrome: str, page: Path, tmp_path: Path, width: int, height: int, timeout: int) -> tuple[str, str, str]:
    """Run `chrome --dump-dom page`; return (stdout, stderr, problem). `problem` is "" on success.

    Output goes to files, not pipes: a browser helper process (crash handler, zygote) that
    outlives the browser inherits a pipe and keeps `communicate()` waiting forever. The whole
    process group is killed afterwards so nothing is left behind.
    """
    work = Path(tempfile.mkdtemp(prefix="run", dir=tmp_path))
    out_path, err_path = work / "stdout.txt", work / "stderr.txt"
    (work / "profile").mkdir()
    cmd = [
        chrome, *_FLAGS, f"--user-data-dir={work / 'profile'}", f"--window-size={width},{height}",
        "--virtual-time-budget=60000", "--dump-dom", page.as_uri(),
    ]
    problem = ""
    posix = os.name != "nt"
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=posix)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            problem = f"browser did not exit within {timeout}s"
        finally:
            try:
                if posix:
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except OSError:
                pass
            proc.wait()
    stdout = out_path.read_text(encoding="utf-8", errors="replace")
    stderr = err_path.read_text(encoding="utf-8", errors="replace")
    if not problem and proc.returncode != 0 and not stdout.strip():
        problem = f"browser exited with code {proc.returncode} and printed nothing"
    return stdout, stderr, problem


_PROBE_PAGE = '<!doctype html><meta charset="utf-8"><title>probe</title><body><script src="probe.js"></script>'
_PROBE_JS = 'document.body.appendChild(Object.assign(document.createElement("pre"), {id: "amb-results", textContent: "[]"}));'
_usable: dict[str, str | None] = {}


def _chromium(tmp_path: Path) -> str:
    """First browser that can load a trivial local page and dump it; skip the test otherwise."""
    if "path" not in _usable:
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir(exist_ok=True)
        (probe_dir / "probe.html").write_text(_PROBE_PAGE, encoding="utf-8")
        (probe_dir / "probe.js").write_text(_PROBE_JS, encoding="utf-8")
        tried: list[str] = []
        _usable.update(path=None, why=None)
        for chrome in _candidates():
            stdout, stderr, problem = _dump_dom(chrome, probe_dir / "probe.html", probe_dir, 800, 600, 30)
            if not problem and 'id="amb-results"' in stdout:
                _usable.update(path=chrome, why=None)
                break
            tried.append(f"{chrome}: {problem or 'probe page did not render'} {stderr[-200:].strip()!r}")
        else:
            _usable["why"] = (
                "no usable Chromium for the panel browser tests (set AMB_CHROMIUM to a working binary): "
                + ("; ".join(tried) if tried else "none found")
            )
    if _usable["path"]:
        return _usable["path"]
    if os.environ.get("AMB_REQUIRE_BROWSER") == "1":
        pytest.fail(_usable["why"])
    pytest.skip(_usable["why"])


def _run_page(tmp_path: Path, page: Path, width: int = 1000, height: int = 800) -> list[dict]:
    chrome = _chromium(tmp_path)
    stdout, stderr, problem = _dump_dom(chrome, page, tmp_path, width, height, LAUNCH_TIMEOUT)
    match = re.search(r'<pre id="amb-results">(.*?)</pre>', stdout, re.S)
    assert match, (
        f"{page.name} never reported results ({problem or 'browser exited normally'}); "
        f"browser={chrome}; stderr tail: {stderr[-400:]!r}; DOM tail: {stdout[-300:]!r}"
    )
    results = json.loads(html.unescape(match.group(1)))
    for r in results:
        assert r["name"] != "__watchdog__", f"{page.name}: {r['error']}"
    return results


def _stage(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    shutil.copytree(PANEL, site / "panel")
    for name in ("lib.js", "stub.js", "app_driver.js", "xss_driver.js"):
        shutil.copy(WEB / name, site / name)
    return site


@pytest.fixture(scope="module")
def app_results(tmp_path_factory) -> list[dict]:
    tmp = tmp_path_factory.mktemp("panel_app")
    site = _stage(tmp)
    page = (site / "panel" / "index.html").read_text(encoding="utf-8")
    # Same page, same CSP; only the stub + runner scripts are added (same origin 'self').
    page = page.replace(
        '  <script src="./vendor/smd.min.js"></script>',
        '  <script src="../lib.js"></script>\n  <script src="../stub.js"></script>\n'
        '  <script src="./vendor/smd.min.js"></script>',
    )
    page = page.replace(
        '  <script src="./app.js"></script>',
        '  <script src="./app.js"></script>\n  <script src="../app_driver.js"></script>',
    )
    assert "../app_driver.js" in page and "../stub.js" in page
    (site / "panel" / "test_index.html").write_text(page, encoding="utf-8")
    return _run_page(tmp, site / "panel" / "test_index.html", width=1000, height=800)


@pytest.fixture(scope="module")
def xss_results(tmp_path_factory) -> list[dict]:
    tmp = tmp_path_factory.mktemp("panel_xss")
    site = _stage(tmp)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>chat xss</title>
<link rel="stylesheet" href="./panel/styles.css"><link rel="stylesheet" href="./panel/chat.css">
</head><body>
<script src="./lib.js"></script>
<script src="./panel/vendor/smd.min.js"></script>
<script src="./panel/vendor/highlight.core-min.js"></script>
<script src="./panel/chat.js"></script>
<script src="./xss_driver.js"></script>
</body></html>"""
    (site / "xss.html").write_text(page, encoding="utf-8")
    return _run_page(tmp, site / "xss.html")


def _names(driver: str) -> list[str]:
    src = (WEB / driver).read_text(encoding="utf-8")
    return re.findall(r'test\("((?:[^"\\]|\\.)*)"', src)


def _xss_names() -> list[str]:
    """Static names of the xss cases (the generated per-case names are listed from the data)."""
    src = (WEB / "xss_driver.js").read_text(encoding="utf-8")
    cases = re.findall(r'^\s+\["((?:[^"\\]|\\.)*)",', src, re.M)
    out = []
    for name in cases:
        out.append("xss: " + name)
        out.append("xss: " + name + " (streamed by character)")
    return out + [n for n in _names("xss_driver.js") if n != "xss: "]


def _check(results: list[dict], name: str) -> None:
    by_name = {r["name"]: r for r in results}
    assert name in by_name, f"case was not run in the browser: {name}"
    got = by_name[name]
    assert got["ok"], got.get("error")


APP_CASES = [n for n in _names("app_driver.js")]


@pytest.mark.parametrize("name", APP_CASES)
def test_panel_app_in_browser(app_results, name):
    _check(app_results, name)


XSS_CASES = _xss_names()


@pytest.mark.parametrize("name", XSS_CASES)
def test_chat_markdown_is_inert_in_browser(xss_results, name):
    _check(xss_results, name)


def test_every_browser_case_is_listed(app_results, xss_results):
    """Cases the pages ran must all be parametrised above, so none can fail unseen."""
    ran_app = {r["name"] for r in app_results}
    ran_xss = {r["name"] for r in xss_results}
    assert ran_app == set(APP_CASES)
    assert ran_xss == set(XSS_CASES)
