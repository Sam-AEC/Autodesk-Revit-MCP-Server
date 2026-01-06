from __future__ import annotations

from pathlib import Path

from ..schemas import OpenDocumentInput, OpenDocumentOutput
from ..security.workspace import WorkspaceMonitor


def open_document(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = OpenDocumentInput(**payload)
    resolved_path = workspace.assert_in_workspace(Path(input_model.file_path))
    output = OpenDocumentOutput(
        document_id=resolved_path.stem,
        title=resolved_path.name,
        model_path=str(resolved_path),
    )
    return output.model_dump()
