from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..errors import WorkspaceViolation


class WorkspaceMonitor:
    def __init__(self, allowed_directories: Sequence[Path]):
        self.allowed_directories = [directory.resolve() for directory in allowed_directories]

    def assert_in_workspace(self, candidate: Path) -> Path:
        candidate = candidate.resolve()
        if not any(candidate.is_relative_to(directory) for directory in self.allowed_directories):
            raise WorkspaceViolation(f"{candidate} is outside the allowed workspace directories")
        return candidate
