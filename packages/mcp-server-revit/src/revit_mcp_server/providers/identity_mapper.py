import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


from ..security.workspace import WorkspaceMonitor
from .base import AECProvider, ProviderTool

logger = logging.getLogger(__name__)


def format_guid_with_hyphens(hex_str: str) -> str:
    """Format a 32-character hex string as a standard GUID (8-4-4-4-12)."""
    if len(hex_str) != 32:
        return hex_str
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"


class AECMapperProvider(AECProvider):
    def __init__(self, workspace: WorkspaceMonitor) -> None:
        self.workspace = workspace
        # Mappings registry: dict storing mapping dicts
        self._mappings: List[Dict[str, str]] = []
        # Index dictionaries for fast lookup
        self._by_revit: Dict[str, Dict[str, str]] = {}
        self._by_ifc: Dict[str, Dict[str, str]] = {}
        self._by_rhino: Dict[str, Dict[str, str]] = {}
        self._init_capabilities()

    def get_identity(self) -> str:
        return "mapper"

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": "mapper",
            "mappings_count": len(self._mappings)
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "aec_translate_id":
            return self._translate_id(arguments)
        elif name == "aec_register_mapping":
            return self._register_mapping(arguments)
        elif name == "aec_map_workspace_path":
            return self._map_workspace_path(arguments)
        else:
            raise ValueError(f"Unknown tool '{name}' on mapper provider")

    def _init_capabilities(self):
        self._capabilities = [
            ProviderTool(
                name="aec_translate_id",
                description="Translate an element identifier between Revit UniqueId/GUID, IFC GlobalId, and custom registered workflows.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string", "description": "The identifier to translate"},
                        "source_format": {
                            "type": "string",
                            "enum": ["revit_unique_id", "ifc_guid", "rhino_uuid"],
                            "description": "Format of the source identifier"
                        },
                        "target_format": {
                            "type": "string",
                            "enum": ["revit_unique_id", "ifc_guid", "rhino_uuid"],
                            "description": "Format to translate the identifier into"
                        }
                    },
                    "required": ["source_id", "source_format", "target_format"]
                }
            ),
            ProviderTool(
                name="aec_register_mapping",
                description="Register custom relationship links between different BIM workflows (e.g. Revit element ID to Rhino object UUID).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "mappings": {
                            "type": "array",
                            "description": "List of mapping relationships to register",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "revit_unique_id": {"type": "string", "description": "Revit UniqueId or GUID (optional)"},
                                    "ifc_guid": {"type": "string", "description": "IFC GlobalId (optional)"},
                                    "rhino_uuid": {"type": "string", "description": "Rhino/Grasshopper object UUID (optional)"}
                                }
                            }
                        }
                    },
                    "required": ["mappings"]
                }
            ),
            ProviderTool(
                name="aec_map_workspace_path",
                description="Map and convert workspace paths between relative formats, Windows absolute format, and POSIX path format.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "The file or directory path to convert"},
                        "target_format": {
                            "type": "string",
                            "enum": ["relative", "absolute_windows", "absolute_posix"],
                            "description": "Target string format for path conversion"
                        }
                    },
                    "required": ["path", "target_format"]
                }
            )
        ]

    def _translate_id(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        source_id = arguments["source_id"]
        source_format = arguments["source_format"]
        target_format = arguments["target_format"]

        if source_format == target_format:
            return {"translated_id": source_id}

        # 1. Check custom registry first
        custom_mapping = self._lookup_custom_mapping(source_id, source_format)
        if custom_mapping and target_format in custom_mapping:
            return {"translated_id": custom_mapping[target_format], "source": "custom_registry"}

        # 2. Deterministic conversion between Revit UniqueId/GUID and IFC GlobalId
        if {source_format, target_format} == {"revit_unique_id", "ifc_guid"}:
            import ifcopenshell.guid  # lazy: heavy import, only needed here

            if source_format == "revit_unique_id":
                try:
                    # Revit UniqueIds consist of a 36-char GUID followed by instance details (e.g., -0002ab1f)
                    guid_part = source_id[:36]
                    # Validate GUID format
                    uuid_obj = uuid.UUID(guid_part)
                    hex_str = uuid_obj.hex
                    compressed = ifcopenshell.guid.compress(hex_str)
                    return {"translated_id": compressed, "source": "deterministic_guid_compression"}
                except Exception as e:
                    return {"translated_id": None, "error": f"Invalid Revit UniqueId/GUID: {e}"}

            elif source_format == "ifc_guid":
                try:
                    expanded_hex = ifcopenshell.guid.expand(source_id)
                    guid_with_hyphens = format_guid_with_hyphens(expanded_hex)
                    return {"translated_id": guid_with_hyphens, "source": "deterministic_ifc_expansion"}
                except Exception as e:
                    return {"translated_id": None, "error": f"Invalid IFC GlobalId: {e}"}

        return {
            "translated_id": None,
            "message": f"No mapping found from format '{source_format}' to '{target_format}' for ID '{source_id}'."
        }

    def _lookup_custom_mapping(self, source_id: str, format_name: str) -> Optional[Dict[str, str]]:
        if format_name == "revit_unique_id":
            # Check GUID prefix as well in case mapping was registered with different suffix
            val = self._by_revit.get(source_id)
            if not val and len(source_id) > 36:
                val = self._by_revit.get(source_id[:36])
            return val
        elif format_name == "ifc_guid":
            return self._by_ifc.get(source_id)
        elif format_name == "rhino_uuid":
            return self._by_rhino.get(source_id)
        return None

    def _register_mapping(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        mappings_list = arguments["mappings"]
        count = 0
        for m in mappings_list:
            # Clean up mapping keys to target format names
            mapping = {}
            for k, v in m.items():
                if v:
                    mapping[k] = str(v)
            
            if not mapping:
                continue

            self._mappings.append(mapping)
            
            # Index it
            if "revit_unique_id" in mapping:
                r_id = mapping["revit_unique_id"]
                self._by_revit[r_id] = mapping
                # Also index base 36-char GUID
                if len(r_id) > 36:
                    self._by_revit[r_id[:36]] = mapping
            if "ifc_guid" in mapping:
                self._by_ifc[mapping["ifc_guid"]] = mapping
            if "rhino_uuid" in mapping:
                self._by_rhino[mapping["rhino_uuid"]] = mapping

            count += 1

        return {"status": "success", "count_registered": count}

    def _map_workspace_path(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        path_str = arguments["path"]
        target_format = arguments["target_format"]

        # Assert path is within allowed directories
        resolved_path = self.workspace.assert_in_workspace(Path(path_str))

        if target_format == "relative":
            # Return relative path to the first allowed workspace directory
            base_dir = self.workspace.allowed_directories[0].resolve()
            try:
                rel = resolved_path.relative_to(base_dir)
                return {"mapped_path": rel.as_posix()}
            except ValueError:
                # If not relative to the first allowed directory, try others
                for allowed in self.workspace.allowed_directories:
                    try:
                        rel = resolved_path.relative_to(allowed.resolve())
                        return {"mapped_path": rel.as_posix()}
                    except ValueError:
                        pass
                return {"mapped_path": resolved_path.as_posix()}

        elif target_format == "absolute_windows":
            # Ensure backslashes are used
            return {"mapped_path": str(resolved_path).replace("/", "\\")}

        elif target_format == "absolute_posix":
            # Ensure forward slashes are used, strip drive letter if converting to clean POSIX
            posix_path = resolved_path.as_posix()
            # If it starts with a drive letter, e.g. C:/path, convert to /c/path
            if len(posix_path) > 1 and posix_path[1] == ":":
                drive = posix_path[0].lower()
                posix_path = f"/{drive}{posix_path[2:]}"
            return {"mapped_path": posix_path}

        return {"mapped_path": str(resolved_path)}

    async def shutdown(self) -> None:
        pass

