from __future__ import annotations

from ..schemas import HealthInput, HealthOutput, HealthStatus


def revit_health(payload: dict) -> dict:
    input_model = HealthInput(**payload)
    output = HealthOutput(status=HealthStatus.healthy, requests_handled=1, message="All systems nominal")
    return output.model_dump()
