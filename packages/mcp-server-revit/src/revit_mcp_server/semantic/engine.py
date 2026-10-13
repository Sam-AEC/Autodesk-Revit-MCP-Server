from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from revit_mcp_server.semantic.models import (
    ElementRecord,
    RelationRecord,
    TypeRecord,
    SourceMetadata,
    Snapshot,
    BBox,
    LocationPoint,
    ParamVal,
)

logger = logging.getLogger(__name__)


def require_snapshot_or_mock(snapshot_id: str, tool: str) -> None:
    """Refuse to fall back to generated mock data unless mock mode is explicit.

    Callers invoke this when ``snapshot_id`` is empty. In bridge (live) mode an
    omitted snapshot must not be answered with synthetic data that looks like
    findings about the open model.
    """
    from revit_mcp_server.config import BridgeMode, config

    if config.mode != BridgeMode.mock:
        raise ValueError(
            f"{tool} requires a snapshot_id when connected to Revit (mode='{config.mode.value}'). "
            "Capture one first with the snapshot tool and pass its snapshot_id; "
            "generated mock data is only used when MCP_REVIT_MODE=mock."
        )


def generate_mock_snapshot() -> Snapshot:
    snapshot_id = f"01J{uuid.uuid4().hex[:23].upper()}"
    taken_at = datetime.now(timezone.utc)
    
    # Create levels
    level1_uid = "c0326e0e-473d-4952-b8ec-f23696541f41-level-1"
    level2_uid = "c0326e0e-473d-4952-b8ec-f23696541f42-level-2"
    wall_uid = "c0326e0e-473d-4952-b8ec-f23696541f43-wall-1"
    door_uid = "c0326e0e-473d-4952-b8ec-f23696541f44-door-1"
    room_unplaced_uid = "c0326e0e-473d-4952-b8ec-f23696541f45-room-unplaced"
    room_placed_uid = "c0326e0e-473d-4952-b8ec-f23696541f46-room-placed"
    
    elements = [
        # Level 1
        ElementRecord(
            uid=level1_uid,
            element_id=100,
            category="OST_Levels",
            cls="Level",
            type_name="Level 1",
            params={
                "Elevation": ParamVal(v=0.0, storage="Double", instance=True, readonly=True)
            }
        ),
        # Level 2
        ElementRecord(
            uid=level2_uid,
            element_id=101,
            category="OST_Levels",
            cls="Level",
            type_name="Level 2",
            params={
                "Elevation": ParamVal(v=4.0, storage="Double", instance=True, readonly=True)
            }
        ),
        # A Wall
        ElementRecord(
            uid=wall_uid,
            element_id=200,
            category="OST_Walls",
            cls="Wall",
            type_uid="wall-type-uid-0001",
            family="Basic Wall",
            type_name="Generic - 200mm",
            level_uid=level1_uid,
            params={
                "Unconnected Height": ParamVal(v=4.0, storage="Double", instance=True),
                "Length": ParamVal(v=10.0, storage="Double", instance=True, readonly=True)
            },
            bbox=BBox(min=[0.0, 0.0, 0.0], max=[10.0, 0.2, 4.0])
        ),
        # A Placed Door in the Wall
        ElementRecord(
            uid=door_uid,
            element_id=300,
            category="OST_Doors",
            cls="FamilyInstance",
            type_uid="door-type-uid-0001",
            family="Single-Flush",
            type_name="0915 x 2134mm",
            level_uid=level1_uid,
            host_uid=wall_uid,
            params={
                "Mark": ParamVal(v="D-101", storage="String", instance=True),
                "FireRating": ParamVal(v="30", storage="String", instance=True)
            },
            location=LocationPoint(xyz=[5.0, 0.0, 0.0], rotation=0.0),
            bbox=BBox(min=[4.5, -0.1, 0.0], max=[5.5, 0.1, 2.1])
        ),
        # An Unplaced Room (OST_Rooms)
        ElementRecord(
            uid=room_unplaced_uid,
            element_id=400,
            category="OST_Rooms",
            cls="Room",
            type_name="Office 1",
            params={
                "Number": ParamVal(v="101", storage="String", instance=True),
                "Area": ParamVal(v=0.0, storage="Double", instance=True, readonly=True)
            }
        ),
        # A Placed Room (OST_Rooms)
        ElementRecord(
            uid=room_placed_uid,
            element_id=401,
            category="OST_Rooms",
            cls="Room",
            type_name="Kitchen",
            level_uid=level1_uid,
            params={
                "Number": ParamVal(v="102", storage="String", instance=True),
                "Area": ParamVal(v=15.5, storage="Double", instance=True, readonly=True)
            },
            location=LocationPoint(xyz=[2.0, 2.0, 0.0])
        )
    ]
    
    relations = [
        RelationRecord(kind="hosts", **{"from": wall_uid, "to": door_uid}),
        RelationRecord(kind="on_level", **{"from": door_uid, "to": level1_uid}),
        RelationRecord(kind="on_level", **{"from": wall_uid, "to": level1_uid}),
        RelationRecord(kind="on_level", **{"from": room_placed_uid, "to": level1_uid})
    ]
    
    types = [
        TypeRecord(
            uid="wall-type-uid-0001",
            category="OST_Walls",
            family="Basic Wall",
            type_name="Generic - 200mm",
            family_source="system"
        ),
        TypeRecord(
            uid="door-type-uid-0001",
            category="OST_Doors",
            family="Single-Flush",
            type_name="0915 x 2134mm",
            family_source="loadable"
        )
    ]
    
    counts = {
        "by_category": {
            "OST_Levels": 2,
            "OST_Walls": 1,
            "OST_Doors": 1,
            "OST_Rooms": 2
        }
    }
    
    return Snapshot(
        schema="amb.snapshot/1",
        snapshot_id=snapshot_id,
        taken_at=taken_at,
        source=SourceMetadata(
            doc_title="Mock_Project.rvt",
            doc_guid="mock-doc-guid-12345",
            units="SI",
            phase_map={"4": "New Construction"}
        ),
        elements=elements,
        relations=relations,
        types=types,
        counts=counts
    )

def _store_snapshot_file(workspace: Any, snapshot_id: str, source_path: Any) -> None:
    """Make sure ``snapshots/{snapshot_id}.json`` exists in the Python workspace.

    The add-in writes under its own workspace environment, which can differ from
    this process's; copy the file across when they do.
    """
    import shutil
    from pathlib import Path

    snapshots_dir = workspace.allowed_directories[0] / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    target = snapshots_dir / f"{snapshot_id}.json"
    if source_path and Path(source_path).resolve() != target.resolve() and not target.exists():
        shutil.copyfile(source_path, target)


async def snapshot_take(workspace: Any, bridge_client_or_provider: Any = None, options: Any = None) -> Snapshot:
    from revit_mcp_server.config import BridgeMode, config

    live = config.mode != BridgeMode.mock
    if bridge_client_or_provider and hasattr(bridge_client_or_provider, "execute_tool"):
        try:
            res = await bridge_client_or_provider.execute_tool("revit_extract_snapshot", dict(options or {}))
            if isinstance(res, dict) and "snapshot" in res:
                return Snapshot(**res["snapshot"])
            if isinstance(res, dict) and res.get("snapshot_id") and res.get("path"):
                # Add-in result: the snapshot was written to disk, not returned inline.
                import json

                with open(res["path"], encoding="utf-8") as f:
                    snapshot = Snapshot(**json.load(f))
                _store_snapshot_file(workspace, snapshot.snapshot_id, res["path"])
                return snapshot
            if live:
                raise RuntimeError(f"Unexpected result from Revit snapshot extraction: {sorted(res) if isinstance(res, dict) else type(res).__name__}")
        except Exception as e:
            if live:
                raise RuntimeError(
                    f"Could not capture a live snapshot from Revit: {e}. "
                    "No mock data is substituted in bridge mode."
                ) from e
            logger.warning(f"Failed to extract snapshot from Revit host: {e}. Falling back to mock snapshot.")
    elif live:
        raise RuntimeError("No Revit provider is available to capture a live snapshot; no mock data is substituted in bridge mode.")

    snapshot = generate_mock_snapshot()

    # Store snapshot in workspace/snapshots folder
    snapshots_dir = workspace.allowed_directories[0] / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshots_dir / f"{snapshot.snapshot_id}.json"

    with open(snapshot_path, "w", encoding="utf-8") as f:
        f.write(snapshot.model_dump_json(by_alias=True, indent=2))

    return snapshot

def snapshot_query(snapshot: Snapshot, filter_dsl: Dict[str, Any]) -> List[ElementRecord]:
    results = []
    
    for el in snapshot.elements:
        match = True
        for key, val in filter_dsl.items():
            if key == "category":
                if isinstance(val, list):
                    if el.category not in val:
                        match = False
                elif el.category != val:
                    match = False
            elif key == "family" and el.family != val:
                match = False
            elif key == "type_name" and el.type_name != val:
                match = False
            elif key == "level_uid" and el.level_uid != val:
                match = False
            elif key == "workset" and el.workset != val:
                match = False
            elif key == "group_uid" and el.group_uid != val:
                match = False
            elif key == "placed":
                # unplaced/placed for rooms
                is_placed = el.level_uid is not None or (el.location is not None and el.location.xyz is not None)
                if val is True and not is_placed:
                    match = False
                elif val is False and is_placed:
                    match = False
            elif key == "parameter":
                # validate parameter requirements
                param_name = val.get("name")
                if param_name:
                    param = el.params.get(param_name)
                    if val.get("empty") is True:
                        if param is not None and param.v is not None and param.v != "":
                            match = False
                    elif "value" in val:
                        expected = val["value"]
                        if param is None or str(param.v) != str(expected):
                            match = False
                            
        if match:
            results.append(el)
            
    return results

def snapshot_diff(snapshot_a: Snapshot, snapshot_b: Snapshot) -> Dict[str, List[Any]]:
    elements_a = {el.uid: el for el in snapshot_a.elements}
    elements_b = {el.uid: el for el in snapshot_b.elements}
    
    added = []
    deleted = []
    modified = []
    
    # 1. Added/Modified
    for uid, el_b in elements_b.items():
        if uid not in elements_a:
            added.append(el_b)
        else:
            el_a = elements_a[uid]
            # Check if modified
            is_mod = False
            
            # Simple metadata checks
            if el_a.type_uid != el_b.type_uid or el_a.level_uid != el_b.level_uid:
                is_mod = True
                
            # Location check
            if el_a.location != el_b.location:
                is_mod = True
                
            # Parameter check
            if el_a.params != el_b.params:
                is_mod = True
                
            if is_mod:
                modified.append(el_b)
                
    # 2. Deleted
    for uid in elements_a:
        if uid not in elements_b:
            deleted.append(uid)
            
    return {
        "added": added,
        "deleted": deleted,
        "modified": modified
    }

def reconcile_delta(
    base: Snapshot, 
    target: Snapshot, 
    live: Snapshot
) -> Dict[str, Any]:
    base_elements = {el.uid: el for el in base.elements}
    live_elements = {el.uid: el for el in live.elements}
    
    conflicts = []
    actions = []
    
    # Identify target modifications or deletions
    target_diff = snapshot_diff(base, target)
    
    # 1. Handle Deleted Elements
    for uid in target_diff["deleted"]:
        # Check if modified in live since base
        base_el = base_elements.get(uid)
        live_el = live_elements.get(uid)
        if base_el and live_el:
            # If live was modified compared to base
            if live_el.params != base_el.params or live_el.location != base_el.location:
                conflicts.append({
                    "uid": uid,
                    "reason": "Element was modified in the live model but is slated for deletion in the target plan."
                })
                continue
        actions.append({
            "action": "delete",
            "uid": uid,
            "element_id": base_el.element_id if base_el else None
        })
        
    # 2. Handle Modified Elements
    for target_el in target_diff["modified"]:
        uid = target_el.uid
        base_el = base_elements.get(uid)
        live_el = live_elements.get(uid)
        
        if not base_el or not live_el:
            # Element missing, cannot reconcile modification
            continue
            
        # Check for conflict: has live changed compared to base?
        live_changed = False
        if live_el.location != base_el.location or live_el.params != base_el.params or live_el.type_uid != base_el.type_uid:
            live_changed = True
            
        if live_changed:
            # Check if target values equal live values (safe) or differ (conflict)
            if target_el.location != live_el.location or target_el.params != live_el.params or target_el.type_uid != live_el.type_uid:
                conflicts.append({
                    "uid": uid,
                    "reason": "Element was modified both in the target plan and in the live model since extraction."
                })
                continue
                
        # Generate parameter updates or location updates
        param_updates = {}
        for p_name, p_val in target_el.params.items():
            base_p = base_el.params.get(p_name)
            if not base_p or base_p.v != p_val.v:
                param_updates[p_name] = p_val.v
                
        actions.append({
            "action": "modify",
            "uid": uid,
            "element_id": target_el.element_id,
            "param_updates": param_updates,
            "location": target_el.location.model_dump() if target_el.location else None
        })
        
    # 3. Handle Added Elements
    for target_el in target_diff["added"]:
        actions.append({
            "action": "create",
            "uid": target_el.uid,
            "category": target_el.category,
            "type_uid": target_el.type_uid,
            "level_uid": target_el.level_uid,
            "location": target_el.location.model_dump() if target_el.location else None,
            "params": {k: v.v for k, v in target_el.params.items()}
        })
        
    return {
        "conflicts": conflicts,
        "actions": actions,
        "reconciled_at": datetime.now(timezone.utc).isoformat()
    }
