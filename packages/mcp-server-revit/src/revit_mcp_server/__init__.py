"""AEC Model Bridge server entrypoint."""

from importlib.metadata import PackageNotFoundError, version as _dist_version

try:
    __version__ = _dist_version("aec-model-bridge")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"

__all__ = ["run_server", "__version__"]


def __getattr__(name: str):
    # Lazy: importing this package (or any submodule, e.g. panel_server) must not
    # have the side effect of building mcp_server's stdio-server registry — that
    # registry does real work at construction (Speckle/APS OAuth setup, a Rhino
    # bridge health probe, ModuleRegistry filesystem discovery), and paying for it
    # on every import regardless of whether the stdio server is even wanted was a
    # real, measurable cost once a second entry point (panel_server.py) existed.
    if name == "run_server":
        from .mcp_server import run_mcp_server
        return run_mcp_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
