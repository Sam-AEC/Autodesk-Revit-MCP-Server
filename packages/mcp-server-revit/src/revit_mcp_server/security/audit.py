from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..schemas import HealthOutput

class AuditRecorder:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, tool: str, request_id: str, payload: dict, response: dict) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "request_id": request_id,
            "payload": payload,
            "response": response,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
