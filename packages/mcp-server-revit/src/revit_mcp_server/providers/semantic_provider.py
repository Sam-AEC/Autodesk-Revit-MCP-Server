from __future__ import annotations

import json
from typing import Any, Dict, List
import uuid

from revit_mcp_server.errors import BridgeError
from revit_mcp_server.providers.base import AECProvider, ProviderTool
from revit_mcp_server.security.workspace import WorkspaceMonitor
from revit_mcp_server.semantic import engine
from revit_mcp_server.semantic.models import Snapshot

class SemanticProvider(AECProvider):
    def __init__(self, workspace: WorkspaceMonitor, registry: Any = None):
        self.workspace = workspace
        self.registry = registry
        self._init_capabilities()

    def get_identity(self) -> str:
        return "semantic"

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": "semantic"
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "snapshot_take":
            return await self._snapshot_take(arguments)
        elif name == "snapshot_query":
            return await self._snapshot_query(arguments)
        elif name == "snapshot_diff":
            return await self._snapshot_diff(arguments)
        else:
            raise BridgeError(f"Unknown tool '{name}' on semantic provider")

    def _init_capabilities(self):
        self._capabilities = [
            ProviderTool(
                name="snapshot_take",
                description="Extract and save a complete semantic BIM snapshot of the active Revit model.",
                inputSchema={"type": "object", "properties": {}, "required": []}
            ),
            ProviderTool(
                name="snapshot_query",
                description="Query element records within a saved snapshot using filter DSL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "snapshot_id": {"type": "string"},
                        "filter": {
                            "type": "object",
                            "properties": {
                                "category": {"type": "string"},
                                "family": {"type": "string"},
                                "type_name": {"type": "string"},
                                "level_uid": {"type": "string"},
                                "placed": {"type": "boolean"},
                                "parameter": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "empty": {"type": "boolean"},
                                        "value": {"type": "string"}
                                    },
                                    "required": ["name"]
                                }
                            }
                        }
                    },
                    "required": ["snapshot_id", "filter"]
                }
            ),
            ProviderTool(
                name="snapshot_diff",
                description="Compare two saved snapshots and identify differences (added, deleted, modified).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "snapshot_a_id": {"type": "string"},
                        "snapshot_b_id": {"type": "string"}
                    },
                    "required": ["snapshot_a_id", "snapshot_b_id"]
                }
            )
        ]

    async def _snapshot_take(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Call bridge server / extract snapshot
        revit_prov = None
        if self.registry:
            revit_prov = self.registry.get_provider("revit")
            
        snapshot = await engine.snapshot_take(self.workspace, revit_prov)
        
        # Identity mapper integration: register mappings in memory
        if self.registry:
            mapper = self.registry.get_provider("mapper")
            if mapper:
                mappings = []
                import ifcopenshell.guid  # lazy: heavy import, only needed here

                for el in snapshot.elements:
                    if el.uid:
                        # Extract GUID prefix deterministically
                        guid_part = el.uid[:36]
                        try:
                            uuid_obj = uuid.UUID(guid_part)
                            ifc_guid = ifcopenshell.guid.compress(uuid_obj.hex)
                        except Exception:
                            ifc_guid = None
                        
                        mappings.append({
                            "revit_unique_id": el.uid,
                            "ifc_guid": ifc_guid
                        })
                if mappings:
                    mapper._register_mapping({"mappings": mappings})
                    
        return {
            "status": "success",
            "snapshot_id": snapshot.snapshot_id,
            "taken_at": snapshot.taken_at.isoformat(),
            "elements_count": len(snapshot.elements)
        }

    async def _snapshot_query(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        snapshot_id = arguments["snapshot_id"]
        filter_dsl = arguments["filter"]
        
        snapshot = self._load_snapshot(snapshot_id)
        elements = engine.snapshot_query(snapshot, filter_dsl)
        
        return {
            "snapshot_id": snapshot_id,
            "matches_count": len(elements),
            "elements": [el.model_dump(by_alias=True) for el in elements]
        }

    async def _snapshot_diff(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        a_id = arguments["snapshot_a_id"]
        b_id = arguments["snapshot_b_id"]
        
        snap_a = self._load_snapshot(a_id)
        snap_b = self._load_snapshot(b_id)
        
        diff = engine.snapshot_diff(snap_a, snap_b)
        
        return {
            "snapshot_a_id": a_id,
            "snapshot_b_id": b_id,
            "added_count": len(diff["added"]),
            "deleted_count": len(diff["deleted"]),
            "modified_count": len(diff["modified"]),
            "added": [el.model_dump(by_alias=True) for el in diff["added"]],
            "deleted": diff["deleted"],
            "modified": [el.model_dump(by_alias=True) for el in diff["modified"]]
        }

    def _load_snapshot(self, snapshot_id: str) -> Snapshot:
        snapshots_dir = self.workspace.allowed_directories[0] / "snapshots"
        snapshot_path = snapshots_dir / f"{snapshot_id}.json"
        
        if not snapshot_path.exists():
            raise BridgeError(f"Snapshot '{snapshot_id}' not found in workspace snapshots directory")
            
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Snapshot(**data)
        except Exception as e:
            raise BridgeError(f"Failed to load snapshot '{snapshot_id}': {e}")

    async def shutdown(self) -> None:
        pass
