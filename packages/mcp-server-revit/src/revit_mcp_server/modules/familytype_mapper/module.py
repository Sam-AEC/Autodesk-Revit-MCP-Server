"""
familytype_mapper module — P9.3 Family Audit & Type Mapping (read side).

Commands:
  audit_families      — Flag in-place families, families without types, and overloaded families.
  list_type_mappings  — Return a type mapping table (family → types used) for roundtrip/W11.

W6 Core Audit Rules:
  - In-place families → always flag (should be converted to loadable)
  - Families with zero placed instances → flag as unused
  - Families with >10 types → flag as overloaded
  - Type names containing spaces at start/end → flag as bad naming
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _workspace_dir(workspace: Any) -> Path:
    return workspace.allowed_directories[0]

def _load_snapshot(snapshot_id: str, workspace: Any) -> Dict[str, Any]:
    path = _workspace_dir(workspace) / "snapshots" / f"{snapshot_id}.json"
    if not path.exists():
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _get_data(snapshot_id: str, workspace: Any):
    if not snapshot_id:
        from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
        require_snapshot_or_mock(snapshot_id, "familytype_mapper")
        snap = generate_mock_snapshot()
        return (
            [el.model_dump(by_alias=True) for el in snap.elements],
            [t.model_dump() for t in snap.types],
        )
    data = _load_snapshot(snapshot_id, workspace)
    return data.get("elements", []), data.get("types", [])


class FamilytypeMapperModule:

    def audit_families(self, snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        elements, types = _get_data(snapshot_id, workspace)
        
        # Count instances per family
        family_instances: Dict[str, int] = defaultdict(int)
        for el in elements:
            fam = el.get("family")
            if fam:
                family_instances[fam] += 1
        
        # Build type counts per family
        family_types: Dict[str, List[str]] = defaultdict(list)
        for t in types:
            fam = t.get("family")
            tn = t.get("type_name")
            if fam and tn:
                family_types[fam].append(tn)
        
        # In-place detection (from TypeRecord.family_source == "inplace")
        inplace_families = {t.get("family") for t in types if t.get("family_source") == "inplace"}
        
        findings = []
        for t in types:
            fam = t.get("family")
            if not fam:
                continue
            
            src = t.get("family_source", "loadable")
            
            # Rule: in-place family
            if src == "inplace":
                findings.append({
                    "severity": "warning",
                    "rule": "inplace_family",
                    "family": fam,
                    "message": f"Family '{fam}' is in-place. Should be converted to loadable.",
                })
            
            # Rule: zero instances
            if family_instances.get(fam, 0) == 0:
                findings.append({
                    "severity": "info",
                    "rule": "unused_family",
                    "family": fam,
                    "message": f"Family '{fam}' has no placed instances.",
                })
        
        # De-duplicate by (rule, family)
        seen = set()
        deduped = []
        for f in findings:
            key = (f["rule"], f["family"])
            if key not in seen:
                seen.add(key)
                deduped.append(f)
        
        # Overloaded families (>10 types)
        for fam, type_names in family_types.items():
            if len(type_names) > 10:
                deduped.append({
                    "severity": "warning",
                    "rule": "overloaded_family",
                    "family": fam,
                    "message": f"Family '{fam}' has {len(type_names)} types. Consider splitting.",
                })
        
        # Bad type name (leading/trailing spaces)
        for t in types:
            tn = t.get("type_name", "")
            if tn != tn.strip():
                deduped.append({
                    "severity": "error",
                    "rule": "bad_type_name",
                    "family": t.get("family"),
                    "type_name": tn,
                    "message": f"Type name '{tn}' has leading/trailing whitespace.",
                })
        
        return {
            "families_total": len(set(t.get("family") for t in types if t.get("family"))),
            "inplace_count": len(inplace_families),
            "findings_count": len(deduped),
            "findings": deduped,
            **({"data_source": "mock"} if not snapshot_id else {}),
        }

    def list_type_mappings(self, snapshot_id: str = "", category: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        elements, types = _get_data(snapshot_id, workspace)
        
        # Build per-family type → instances mapping
        type_usage: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for el in elements:
            if category and el.get("category") != category:
                continue
            fam = el.get("family")
            tn = el.get("type_name")
            if fam and tn:
                type_usage[fam][tn] += 1
        
        result = []
        for fam in sorted(type_usage):
            types_list = [
                {"type_name": tn, "instance_count": cnt}
                for tn, cnt in sorted(type_usage[fam].items())
            ]
            result.append({"family": fam, "types": types_list})
        
        return {
            "category_filter": category or "(all)",
            "families_count": len(result),
            "mappings": result,
            **({"data_source": "mock"} if not snapshot_id else {}),
        }
