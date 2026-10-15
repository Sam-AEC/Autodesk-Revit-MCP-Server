"""
model_inspector module — P7.1/P7.2/P7.3 Model Inspection Workflows.

Commands:
  summarize_model     — Category counts + element type summary.
  ask                 — NL-style DSL query against snapshot.
  list_groups         — List all model groups (members + instance count).
  inspect_selection   — Element card: type/host/level/params/warnings.
  save_query          — Persist a named DSL filter to workspace.
  run_saved_query     — Re-run a named saved query against snapshot.
  list_saved_queries  — Enumerate saved queries.
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SAVED_QUERIES_FILE = "saved_queries.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshots_dir(workspace: Any) -> Path:
    return workspace.allowed_directories[0] / "snapshots"

def _queries_file(workspace: Any) -> Path:
    return workspace.allowed_directories[0] / SAVED_QUERIES_FILE

def _load_snapshot(snapshot_id: str, workspace: Any) -> Dict[str, Any]:
    path = _snapshots_dir(workspace) / f"{snapshot_id}.json"
    if not path.exists():
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _load_queries(workspace: Any) -> Dict[str, Any]:
    qfile = _queries_file(workspace)
    if qfile.exists():
        with open(qfile, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_queries(queries: Dict[str, Any], workspace: Any) -> None:
    qfile = _queries_file(workspace)
    with open(qfile, "w", encoding="utf-8") as f:
        json.dump(queries, f, indent=2)

def _match_element(el: Dict[str, Any], filter_dsl: Dict[str, Any]) -> bool:
    """Apply DSL filter to a raw element dict (mirrors engine.snapshot_query logic)."""
    for key, val in filter_dsl.items():
        if key == "category":
            cats = val if isinstance(val, list) else [val]
            if el.get("category") not in cats:
                return False
        elif key == "family" and el.get("family") != val:
            return False
        elif key == "type_name" and el.get("type_name") != val:
            return False
        elif key == "level_uid" and el.get("level_uid") != val:
            return False
        elif key == "workset" and el.get("workset") != val:
            return False
        elif key == "group_uid" and el.get("group_uid") != val:
            return False
        elif key == "placed":
            is_placed = el.get("level_uid") is not None or el.get("location") is not None
            if val and not is_placed:
                return False
            elif not val and is_placed:
                return False
        elif key == "parameter":
            pname = val.get("name")
            params = el.get("params", {})
            param = params.get(pname) if params else None
            if val.get("empty") is True:
                if param is not None and param.get("v") not in (None, ""):
                    return False
            elif "value" in val:
                if param is None or str(param.get("v")) != str(val["value"]):
                    return False
    return True

def _element_chip(el: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight element chip for panel display."""
    return {
        "uid": el["uid"],
        "element_id": el.get("element_id"),
        "label": el.get("type_name") or el.get("category", ""),
        "category": el.get("category"),
        "family": el.get("family"),
        "type_name": el.get("type_name"),
        "level_uid": el.get("level_uid"),
    }


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

class ModelInspectorModule:

    def summarize_model(self, snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        is_mock = False
        if not snapshot_id:
            # Auto-take snapshot — call out to semantic module
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
            require_snapshot_or_mock(snapshot_id, "model_inspector")
            is_mock = True
            snap = generate_mock_snapshot()
            elements = [el.model_dump(by_alias=True) for el in snap.elements]
            types = [t.model_dump() for t in snap.types]
            source = snap.source.model_dump()
        else:
            data = _load_snapshot(snapshot_id, workspace)
            elements = data.get("elements", [])
            types = data.get("types", [])
            source = data.get("source", {})

        by_cat: Counter = Counter(el.get("category") for el in elements)
        family_set = set(
            el.get("family") for el in elements if el.get("family")
        )
        type_count = len(types)

        # Count placed/unplaced rooms
        rooms = [el for el in elements if el.get("category") == "OST_Rooms"]
        placed_rooms = sum(
            1 for r in rooms if r.get("level_uid") or r.get("location")
        )

        return {
            "doc_title": source.get("doc_title", ""),
            "doc_guid": source.get("doc_guid", ""),
            "elements_total": len(elements),
            "types_total": type_count,
            "family_count": len(family_set),
            "by_category": dict(by_cat.most_common()),
            "rooms": {"total": len(rooms), "placed": placed_rooms, "unplaced": len(rooms) - placed_rooms},
            **({"data_source": "mock"} if is_mock else {}),
        }

    def ask(self, filter: Dict[str, Any], snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        is_mock = False
        if not snapshot_id:
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
            require_snapshot_or_mock(snapshot_id, "model_inspector")
            is_mock = True
            snap = generate_mock_snapshot()
            elements = [el.model_dump(by_alias=True) for el in snap.elements]
        else:
            data = _load_snapshot(snapshot_id, workspace)
            elements = data.get("elements", [])

        matched = [el for el in elements if _match_element(el, filter)]
        chips = [_element_chip(el) for el in matched]

        return {
            "filter": filter,
            "matches_count": len(chips),
            "elements": chips,
            **({"data_source": "mock"} if is_mock else {}),
        }

    def list_groups(self, snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        is_mock = False
        if not snapshot_id:
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
            require_snapshot_or_mock(snapshot_id, "model_inspector")
            is_mock = True
            snap = generate_mock_snapshot()
            elements = [el.model_dump(by_alias=True) for el in snap.elements]
        else:
            data = _load_snapshot(snapshot_id, workspace)
            elements = data.get("elements", [])

        # Collect group members
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for el in elements:
            gid = el.get("group_uid")
            if gid:
                groups[gid].append(_element_chip(el))

        group_list = [
            {"group_uid": gid, "member_count": len(members), "members": members}
            for gid, members in groups.items()
        ]

        return {
            "groups_count": len(group_list),
            "groups": group_list,
            **({"data_source": "mock"} if is_mock else {}),
        }

    def inspect_selection(self, element_uids: List[str], snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        is_mock = False
        if not snapshot_id:
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
            require_snapshot_or_mock(snapshot_id, "model_inspector")
            is_mock = True
            snap = generate_mock_snapshot()
            elements = {el.uid: el.model_dump(by_alias=True) for el in snap.elements}
        else:
            data = _load_snapshot(snapshot_id, workspace)
            elements = {el["uid"]: el for el in data.get("elements", [])}

        cards = []
        missing = []
        for uid in element_uids:
            el = elements.get(uid)
            if not el:
                missing.append(uid)
                continue

            warnings = []
            # Basic BIM quality warnings
            if el.get("category") == "OST_Rooms":
                area = (el.get("params", {}).get("Area") or {}).get("v", 0)
                if not (el.get("level_uid") or el.get("location")):
                    warnings.append("Room is not placed")
                elif area == 0:
                    warnings.append("Room has zero area (not enclosed)")
                mark = (el.get("params", {}).get("Number") or {}).get("v")
                if not mark:
                    warnings.append("Room has no Number parameter set")

            if el.get("category") in ("OST_Doors", "OST_Windows"):
                mark = (el.get("params", {}).get("Mark") or {}).get("v")
                if not mark:
                    warnings.append("Element has no Mark parameter")

            cards.append({
                "uid": el["uid"],
                "element_id": el.get("element_id"),
                "category": el.get("category"),
                "family": el.get("family"),
                "type_name": el.get("type_name"),
                "host_uid": el.get("host_uid"),
                "level_uid": el.get("level_uid"),
                "workset": el.get("workset"),
                "group_uid": el.get("group_uid"),
                "location": el.get("location"),
                "params": el.get("params", {}),
                "warnings": warnings,
            })

        return {
            "inspected_count": len(cards),
            "missing_uids": missing,
            "elements": cards,
            **({"data_source": "mock"} if is_mock else {}),
        }

    def save_query(self, query_name: str, filter: Dict[str, Any], workspace: Any = None, **_) -> Dict[str, Any]:
        queries = _load_queries(workspace)
        queries[query_name] = filter
        _save_queries(queries, workspace)
        return {"status": "saved", "query_name": query_name, "filter": filter}

    def run_saved_query(self, query_name: str, snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        queries = _load_queries(workspace)
        if query_name not in queries:
            raise ValueError(f"No saved query named '{query_name}'.")
        filter_dsl = queries[query_name]
        return self.ask(filter=filter_dsl, snapshot_id=snapshot_id, workspace=workspace)

    def list_saved_queries(self, workspace: Any = None, **_) -> Dict[str, Any]:
        queries = _load_queries(workspace)
        return {
            "count": len(queries),
            "queries": [{"name": k, "filter": v} for k, v in queries.items()],
        }
