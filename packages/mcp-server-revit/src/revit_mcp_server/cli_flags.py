"""--help and --version for the long-running console scripts.

The stdio server and the panel server are started by clients with no arguments.
Without this, `aec-model-bridge --help` silently started the server and waited
for input. Unknown arguments are ignored so existing client configs keep working.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence


def handle_standard_flags(prog: str, description: str, argv: Sequence[str] | None = None) -> None:
    from . import __version__

    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument("--version", action="version", version=f"{prog} {__version__}")
    parser.parse_known_args(argv)
