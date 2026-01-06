from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Dict

from ..schemas import (
    BaselineDiffInput,
    BaselineDiffOutput,
    BaselineExportInput,
    BaselineExportOutput,
    ExportQuantitiesInput,
    ExportQuantitiesOutput,
    ExportResult,
    ExportSchedulesInput,
    ExportSchedulesOutput,
    GenericAuditInput,
    GenericAuditOutput,
    HealthInput,
    HealthOutput,
    HealthStatus,
    ListViewsInput,
    ListViewsOutput,
    OpenDocumentInput,
    OpenDocumentOutput,
    RequestPayload,
    SheetBatchInput,
    SheetBatchOutput,
)
from ..security.workspace import WorkspaceMonitor

ToolHandler = Callable[[dict, WorkspaceMonitor], dict]


def _record_request(payload: RequestPayload) -> None:
    payload.request_id  # type: ignore


def revit_health(payload: dict, _: WorkspaceMonitor) -> dict:
    input_model = HealthInput(**payload)
    _record_request(input_model)
    return HealthOutput(status=HealthStatus.healthy, requests_handled=1, message="Bridge ready").model_dump()


def open_document(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = OpenDocumentInput(**payload)
    resolved = workspace.assert_in_workspace(Path(input_model.file_path))
    return OpenDocumentOutput(
        document_id=resolved.stem,
        title=resolved.name,
        model_path=str(resolved),
    ).model_dump()


def list_views(payload: dict, _: WorkspaceMonitor) -> dict:
    _record_request(ListViewsInput(**payload))
    views = [
        {"view_id": "view-1", "name": "Floor Plan", "discipline": "Architectural"},
        {"view_id": "view-2", "name": "Ceiling Plan", "discipline": "Mechanical"},
    ]
    return ListViewsOutput(views=views).model_dump()


def export_schedules(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = ExportSchedulesInput(**payload)
    output_marker = WorkspaceMonitor(workspace.allowed_directories).assert_in_workspace(
        Path(input_model.output_path)
    )
    data = ["Schedule A", "Schedule B"]
    return ExportSchedulesOutput(schedules=data, output_path=str(output_marker)).model_dump()


def export_quantities(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = ExportQuantitiesInput(**payload)
    output_marker = workspace.assert_in_workspace(Path(input_model.output_path))
    return ExportQuantitiesOutput(categories_exported=5, output_path=str(output_marker)).model_dump()


def baseline_export(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = BaselineExportInput(**payload)
    path = workspace.assert_in_workspace(Path(input_model.output_path))
    return BaselineExportOutput(snapshot_id=f"baseline-{datetime.utcnow().isoformat()}", output_path=str(path)).model_dump()


def baseline_diff(payload: dict, _: WorkspaceMonitor) -> dict:
    input_model = BaselineDiffInput(**payload)
    return BaselineDiffOutput(differences=[f"diff between {input_model.baseline_a} and {input_model.baseline_b}"]).model_dump()


def sheet_batch_from_csv(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = SheetBatchInput(**payload)
    workspace.assert_in_workspace(Path(input_model.csv_path))
    return SheetBatchOutput(sheets_created=3).model_dump()


def export_pdf_by_sheet(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = SheetBatchInput(**payload)
    workspace.assert_in_workspace(Path(input_model.csv_path))
    return ExportResult(
        file_path=str(Path(workspace.allowed_directories[0]) / "export.pdf"),
        status="mocked",
    ).model_dump()


def export_dwg_by_sheet(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = SheetBatchInput(**payload)
    workspace.assert_in_workspace(Path(input_model.csv_path))
    return ExportResult(
        file_path=str(Path(workspace.allowed_directories[0]) / "export.dwg"),
        status="mocked",
    ).model_dump()


def export_ifc_named_setup(payload: dict, workspace: WorkspaceMonitor) -> dict:
    input_model = SheetBatchInput(**payload)
    workspace.assert_in_workspace(Path(input_model.csv_path))
    return ExportResult(
        file_path=str(Path(workspace.allowed_directories[0]) / "setup.ifc"),
        status="mocked",
    ).model_dump()


def generic_audit(payload: dict, _: WorkspaceMonitor) -> dict:
    input_model = GenericAuditInput(**payload)
    return GenericAuditOutput(issues_found=0).model_dump()


TOOL_HANDLERS: Dict[str, ToolHandler] = {
    "revit.health": revit_health,
    "revit.open_document": open_document,
    "revit.list_views": list_views,
    "revit.model_health_summary": generic_audit,
    "revit.warning_triage_report": generic_audit,
    "revit.naming_standards_audit": generic_audit,
    "revit.parameter_compliance_audit": generic_audit,
    "revit.shared_parameter_binding_audit": generic_audit,
    "revit.view_template_compliance_check": generic_audit,
    "revit.tag_coverage_audit": generic_audit,
    "revit.room_space_completeness_report": generic_audit,
    "revit.link_monitor_report": generic_audit,
    "revit.coordinate_sanity_check": generic_audit,
    "revit.export_schedules": export_schedules,
    "revit.export_quantities": export_quantities,
    "revit.baseline_export": baseline_export,
    "revit.baseline_diff": baseline_diff,
    "revit.batch_create_sheets_from_csv": sheet_batch_from_csv,
    "revit.batch_place_views_on_sheets": generic_audit,
    "revit.titleblock_fill_from_csv": generic_audit,
    "revit.create_print_set": generic_audit,
    "revit.export_pdf_by_sheet_set": export_pdf_by_sheet,
    "revit.export_dwg_by_sheet_set": export_dwg_by_sheet,
    "revit.export_ifc_named_setup": export_ifc_named_setup,
    "revit.publish_package_builder": generic_audit,
    "revit.export_report": generic_audit,
}
