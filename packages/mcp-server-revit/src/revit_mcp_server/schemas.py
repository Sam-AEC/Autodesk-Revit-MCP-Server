from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RequestPayload(BaseModel):
    request_id: str = Field(..., description="Unique tool invocation ID")


class HealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    failing = "failing"


class HealthInput(RequestPayload):
    check_interval: Optional[int] = Field(30, description="Seconds between bridge health retries")


class HealthOutput(BaseModel):
    status: HealthStatus
    requests_handled: int = Field(0)
    message: str = Field("Bridge connectivity is verified.")


class OpenDocumentInput(RequestPayload):
    file_path: str
    detach: bool = False


class OpenDocumentOutput(BaseModel):
    document_id: str
    title: str
    model_path: str


class ListViewsInput(RequestPayload):
    document_id: Optional[str] = None


class ViewSummary(BaseModel):
    view_id: str
    name: str
    discipline: str


class ListViewsOutput(BaseModel):
    views: List[ViewSummary]


class ExportSchedulesInput(RequestPayload):
    output_path: str


class ExportSchedulesOutput(BaseModel):
    schedules: List[str]
    output_path: str


class ExportQuantitiesInput(RequestPayload):
    output_path: str


class ExportQuantitiesOutput(BaseModel):
    categories_exported: int
    output_path: str


class BaselineExportInput(RequestPayload):
    output_path: str


class BaselineExportOutput(BaseModel):
    snapshot_id: str
    output_path: str


class BaselineDiffInput(RequestPayload):
    baseline_a: str
    baseline_b: str


class BaselineDiffOutput(BaseModel):
    differences: List[str]


class SheetBatchInput(RequestPayload):
    csv_path: str


class SheetBatchOutput(BaseModel):
    sheets_created: int


class PrintSetInput(RequestPayload):
    sheet_set: str


class ExportResult(BaseModel):
    file_path: str
    status: str


class GenericAuditInput(RequestPayload):
    document_id: Optional[str] = None


class GenericAuditOutput(BaseModel):
    issues_found: int
    severity: str = "info"


""": Additional tool schemas can follow this pattern and reuse GenericAuditInput/Output when appropriate."""
