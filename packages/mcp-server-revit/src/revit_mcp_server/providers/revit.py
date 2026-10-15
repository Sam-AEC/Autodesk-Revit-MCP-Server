import logging
from pathlib import Path
from typing import Any, Dict, List

import httpx

from ..bridge.client import BridgeClient
from ..bridge.mock import MockBridge
from ..config import BridgeMode, config
from ..errors import BridgeError, WorkspaceViolation
from ..legacy.tools import TOOL_HANDLERS
from ..security.workspace import WorkspaceMonitor
from .base import AECProvider, ProviderTool, enrich_mutation_metadata

logger = logging.getLogger(__name__)


class UnavailableBridge:
    def __init__(self, message: str) -> None:
        self.message = message

    def initialize(self) -> None:
        return None

    def _get(self, path: str) -> Dict[str, Any]:
        return {"status": "unhealthy", "error": self.message}

    def send_tool(self, tool_name: str, payload: dict) -> dict:
        raise BridgeError(self.message)


class RevitProvider(AECProvider):
    def __init__(
        self,
        workspace: WorkspaceMonitor,
        mode: BridgeMode = config.mode,
        bridge_url: str | None = config.bridge_url,
        host_version: str | None = config.host_version,
        bridge_factory=None,
    ) -> None:
        self.workspace = workspace
        self.mode = mode
        self.bridge_url = bridge_url
        self.host_version = host_version
        self._bridge = self._build_bridge(bridge_factory)
        self._init_tool_mapping()
        self._enrich_tool_metadata()

    def _enrich_tool_metadata(self) -> None:
        mutating_verbs = {
            "create",
            "place",
            "set",
            "delete",
            "save",
            "close",
            "renumber",
            "duplicate",
            "move",
            "copy",
            "rotate",
            "mirror",
            "pin",
            "unpin",
            "sync",
            "relinquish",
            "convert",
            "edit",
            "apply",
            "change",
            "replace",
            "invoke",
            "populate",
            "tag",
            "ungroup",
        }
        enrich_mutation_metadata(
            self._capabilities, mutating_verbs=mutating_verbs, destructive={"revit_execute_python"}
        )

    def get_identity(self) -> str:
        return "revit"

    def _build_bridge(self, factory=None):
        if self.mode == BridgeMode.bridge:
            from ..bridge.discovery import available_host_versions, select_switch

            url = self.bridge_url
            token = None

            if not url:
                switch = select_switch("revit", self.host_version)
                if switch:
                    url = switch.endpoint
                    token = switch.session_token
                    logger.info(
                        "Resolved Revit %s switch from registry: %s",
                        switch.host_version,
                        url,
                    )
                elif self.host_version:
                    versions = available_host_versions("revit")
                    available = ", ".join(versions) if versions else "none"
                    message = (
                        f"No live Revit {self.host_version} bridge found. "
                        f"Available Revit versions: {available}."
                    )
                    logger.warning(message)
                    return UnavailableBridge(message)
                else:
                    url = "http://127.0.0.1:3000"
                    for port in (3000, 3002):
                        probe_url = f"http://127.0.0.1:{port}"
                        try:
                            resp = httpx.get(f"{probe_url}/health", timeout=0.5)
                            if resp.status_code == 200:
                                url = probe_url
                                break
                        except Exception:
                            continue

                    logger.warning(
                        "No Revit switch found in registry, falling back to legacy port %s. "
                        "Tokenless connections are deprecated.",
                        url,
                    )

            bridge_factory = factory or (lambda u, t=None: BridgeClient(u, token=t))
            bridge = bridge_factory(url, token)
            if hasattr(bridge, "initialize"):
                try:
                    bridge.initialize()
                except Exception as e:
                    logger.error(f"Failed to initialize Revit Bridge client: {e}")
            return bridge
        return MockBridge()

    def get_capabilities(self) -> List[ProviderTool]:
        # Defined below to keep the class readable.
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        if self.mode == BridgeMode.bridge:
            try:
                # Direct check
                if hasattr(self._bridge, "_get"):
                    return self._bridge._get("/health")
                return {"status": "healthy", "mode": "bridge"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}
        return {"status": "healthy", "mode": "mock"}

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Check path parameters for workspace compliance
        self._assert_paths_in_workspace(arguments)

        if "." in name:
            # Legacy dot notation (e.g. "revit.health")
            bridge_tool = name
            payload = arguments
        else:
            # MCP underscore notation (e.g. "revit_health")
            normalized_name = name
            if normalized_name not in self._tool_mapping:
                raise ValueError(f"Unknown Revit tool '{name}'")
            bridge_tool, payload_builder = self._tool_mapping[normalized_name]
            payload = payload_builder(arguments)
            if "request_id" in arguments and "request_id" not in payload:
                payload["request_id"] = arguments["request_id"]

        if self.mode == BridgeMode.bridge:
            # Under bridge mode, run the legacy handler for validation/prep only — its
            # return value is discarded, the bridge call below is the real result.
            legacy_dot_name = bridge_tool
            handler = TOOL_HANDLERS.get(legacy_dot_name)
            if handler:
                try:
                    handler({"request_id": "mcp-bridge", **payload}, self.workspace)
                except WorkspaceViolation:
                    # A workspace-sandbox escape must always block the call — swallowing
                    # this as a warning would let a path-outside-workspace request reach
                    # the live bridge anyway, silently defeating the sandbox for every
                    # tool that happens to have a legacy handler.
                    raise
                except Exception as e:
                    # Other legacy-schema validation failures are advisory only: these
                    # Pydantic input models predate the current provider architecture
                    # and can drift out of sync with what the bridge actually accepts.
                    logger.warning(f"Revit legacy handler validation warning: {e}")

            # Send to bridge client
            return self._bridge.send_tool(bridge_tool, payload)
        else:
            # Mock mode
            legacy_dot_name = bridge_tool
            handler = TOOL_HANDLERS.get(legacy_dot_name)
            if handler:
                # The legacy handlers' models require a request_id, which the MCP
                # tool schemas do not expose. Supply one for the handler only, so a
                # plain tool call (for example from a registry introspecting the
                # server in mock mode) does not fail validation.
                return handler({"request_id": "mcp-mock", **payload}, self.workspace)

            # Fallback to general mock response
            return self._bridge.send_tool(bridge_tool, payload)

    def _assert_paths_in_workspace(self, arguments: Dict[str, Any]) -> None:
        path_keys = ["path", "csv_path", "output_path", "file_path", "template_path"]
        for key in path_keys:
            if key in arguments and isinstance(arguments[key], str):
                self.workspace.assert_in_workspace(Path(arguments[key]))

    @staticmethod
    def _placement_location(args: Dict[str, Any]) -> Dict[str, Any]:
        location = args.get("location")
        if location is not None:
            if not isinstance(location, dict):
                raise ValueError("location must be an object with x, y, and optional z coordinates")
            return {
                "x": location.get("x"),
                "y": location.get("y"),
                "z": location.get("z", 0),
            }

        return {
            "x": args.get("x"),
            "y": args.get("y"),
            "z": args.get("z", 0),
        }

    def _init_tool_mapping(self):
        self._tool_mapping = {
            "revit_health": ("revit.health", lambda args: {}),
            "revit_list_levels": ("revit.list_levels", lambda args: {}),
            "revit_list_views": ("revit.list_views", lambda args: {}),
            "revit_get_document_info": ("revit.get_document_info", lambda args: {}),
            "revit_list_elements": (
                "revit.list_elements_by_category",
                lambda args: {"category": args.get("category", "Walls")},
            ),
            "revit_create_wall": (
                "revit.create_wall",
                lambda args: {
                    "start_point": {
                        "x": args.get("start_x", 0),
                        "y": args.get("start_y", 0),
                        "z": args.get("start_z", 0),
                    },
                    "end_point": {"x": args.get("end_x", 0), "y": args.get("end_y", 0), "z": args.get("end_z", 0)},
                    "height": args.get("height", 10),
                    "level": args.get("level", "L1"),
                },
            ),
            "revit_create_floor": (
                "revit.create_floor",
                lambda args: {
                    "boundary_points": [
                        {"x": p.get("x", 0), "y": p.get("y", 0), "z": p.get("z", 0)} for p in args.get("points", [])
                    ],
                    "level": args.get("level", "L1"),
                },
            ),
            "revit_create_roof": (
                "revit.create_roof",
                lambda args: {
                    "boundary_points": [
                        {"x": p.get("x", 0), "y": p.get("y", 0), "z": p.get("z", 0)} for p in args.get("points", [])
                    ],
                    "level": args.get("level", "Level 2"),
                    "slope": args.get("slope", 0.5),
                },
            ),
            "revit_create_level": (
                "revit.create_level",
                lambda args: {"name": args.get("name", "New Level"), "elevation": args.get("elevation", 10)},
            ),
            "revit_save_document": ("revit.save_document", lambda args: {"path": args.get("path", "")}),
            "revit_create_grid": (
                "revit.create_grid",
                lambda args: {
                    "start_point": {"x": args.get("start_x"), "y": args.get("start_y"), "z": args.get("start_z", 0)},
                    "end_point": {"x": args.get("end_x"), "y": args.get("end_y"), "z": args.get("end_z", 0)},
                    "name": args.get("name"),
                },
            ),
            "revit_create_room": (
                "revit.create_room",
                lambda args: {
                    "level": args.get("level"),
                    "location_point": {"x": args.get("x"), "y": args.get("y"), "z": 0},
                    "name": args.get("name"),
                    "number": args.get("number"),
                },
            ),
            "revit_delete_element": ("revit.delete_element", lambda args: {"element_id": args.get("element_id")}),
            "revit_place_family_instance": (
                "revit.place_family_instance",
                lambda args: {
                    "family_name": args.get("family_name"),
                    "type_name": args.get("type_name"),
                    "level": args.get("level"),
                    "location": {"x": args.get("x"), "y": args.get("y"), "z": args.get("z", 0)},
                },
            ),
            "revit_place_door": (
                "revit.place_door",
                lambda args: {
                    "wall_id": args.get("wall_id"),
                    "family_name": args.get("family_name"),
                    "type_name": args.get("type_name"),
                    "location": self._placement_location(args),
                },
            ),
            "revit_place_window": (
                "revit.place_window",
                lambda args: {
                    "wall_id": args.get("wall_id"),
                    "family_name": args.get("family_name"),
                    "type_name": args.get("type_name"),
                    "location": self._placement_location(args),
                },
            ),
            "revit_list_families": ("revit.list_families", lambda args: {}),
            "revit_create_floor_plan_view": (
                "revit.create_floor_plan_view",
                lambda args: {"level_name": args.get("level_name"), "view_name": args.get("view_name")},
            ),
            "revit_create_3d_view": ("revit.create_3d_view", lambda args: {"view_name": args.get("view_name")}),
            "revit_create_section_view": (
                "revit.create_section_view",
                lambda args: {
                    "view_name": args.get("view_name"),
                    "start_point": {"x": args.get("start_x"), "y": args.get("start_y"), "z": args.get("start_z", 0)},
                    "end_point": {"x": args.get("end_x"), "y": args.get("end_y"), "z": args.get("end_z", 0)},
                    "height": args.get("height", 10),
                },
            ),
            "revit_get_element_parameters": (
                "revit.get_element_parameters",
                lambda args: {"element_id": args.get("element_id")},
            ),
            "revit_set_parameter_value": (
                "revit.set_parameter_value",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "parameter_name": args.get("parameter_name"),
                    "value": args.get("value"),
                },
            ),
            "revit_get_parameter_value": (
                "revit.get_parameter_value",
                lambda args: {"element_id": args.get("element_id"), "parameter_name": args.get("parameter_name")},
            ),
            "revit_list_shared_parameters": ("revit.list_shared_parameters", lambda args: {}),
            "revit_create_shared_parameter": (
                "revit.create_shared_parameter",
                lambda args: {
                    "name": args.get("name"),
                    "group": args.get("group", "General"),
                    "type": args.get("type", "Text"),
                    "visible": args.get("visible", True),
                },
            ),
            "revit_list_project_parameters": ("revit.list_project_parameters", lambda args: {}),
            "revit_create_project_parameter": (
                "revit.create_project_parameter",
                lambda args: {
                    "name": args.get("name"),
                    "group": args.get("group", "General"),
                    "type": args.get("type", "Text"),
                    "category": args.get("category"),
                    "visible": args.get("visible", True),
                },
            ),
            "revit_batch_set_parameters": (
                "revit.batch_set_parameters",
                lambda args: {
                    "element_ids": args.get("element_ids"),
                    "parameter_name": args.get("parameter_name"),
                    "value": args.get("value"),
                },
            ),
            "revit_get_type_parameters": (
                "revit.get_type_parameters",
                lambda args: {"element_id": args.get("element_id")},
            ),
            "revit_set_type_parameter": (
                "revit.set_type_parameter",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "parameter_name": args.get("parameter_name"),
                    "value": args.get("value"),
                },
            ),
            "revit_list_sheets": ("revit.list_sheets", lambda args: {}),
            "revit_create_sheet": (
                "revit.create_sheet",
                lambda args: {
                    "name": args.get("name"),
                    "number": args.get("number"),
                    "titleblock_id": args.get("titleblock_id"),
                },
            ),
            "revit_delete_sheet": ("revit.delete_sheet", lambda args: {"sheet_id": args.get("sheet_id")}),
            "revit_place_viewport_on_sheet": (
                "revit.place_viewport_on_sheet",
                lambda args: {
                    "sheet_id": args.get("sheet_id"),
                    "view_id": args.get("view_id"),
                    "location": {"x": args.get("x"), "y": args.get("y"), "z": 0},
                },
            ),
            "revit_batch_create_sheets_from_csv": (
                "revit.batch_create_sheets_from_csv",
                lambda args: {"csv_path": args.get("csv_path"), "titleblock_name": args.get("titleblock_name")},
            ),
            "revit_populate_titleblock": (
                "revit.populate_titleblock",
                lambda args: {"sheet_id": args.get("sheet_id"), "parameters": args.get("parameters")},
            ),
            "revit_list_titleblocks": ("revit.list_titleblocks", lambda args: {}),
            "revit_get_sheet_info": ("revit.get_sheet_info", lambda args: {"sheet_id": args.get("sheet_id")}),
            "revit_duplicate_sheet": (
                "revit.duplicate_sheet",
                lambda args: {
                    "sheet_id": args.get("sheet_id"),
                    "with_views": args.get("with_views", False),
                    "duplicate_option": args.get("duplicate_option", "Duplicate"),
                },
            ),
            "revit_renumber_sheets": (
                "revit.renumber_sheets",
                lambda args: {"prefix": args.get("prefix"), "start_number": args.get("start_number")},
            ),
            "revit_get_selection": ("revit.get_selection", lambda args: {}),
            "revit_set_selection": ("revit.set_selection", lambda args: {"element_ids": args.get("element_ids")}),
            "revit_select_by_unique_ids": (
                "revit.select_by_unique_ids",
                lambda args: {"element_uids": args.get("element_uids")},
            ),
            "revit_create_text_note": (
                "revit.create_text_note",
                lambda args: {
                    "text": args.get("text"),
                    "location": {"x": args.get("x"), "y": args.get("y"), "z": 0},
                    "view_id": args.get("view_id"),
                },
            ),
            "revit_create_tag": (
                "revit.create_tag",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "location": {"x": args.get("x"), "y": args.get("y"), "z": 0},
                    "view_id": args.get("view_id"),
                },
            ),
            "revit_create_column": (
                "revit.create_column",
                lambda args: {
                    "family_name": args.get("family_name"),
                    "type_name": args.get("type_name"),
                    "level": args.get("level"),
                    "location": {"x": args.get("x"), "y": args.get("y"), "z": 0},
                },
            ),
            "revit_create_beam": (
                "revit.create_beam",
                lambda args: {
                    "family_name": args.get("family_name"),
                    "type_name": args.get("type_name"),
                    "level": args.get("level"),
                    "start_point": {"x": args.get("start_x"), "y": args.get("start_y"), "z": 0},
                    "end_point": {"x": args.get("end_x"), "y": args.get("end_y"), "z": 0},
                },
            ),
            "revit_create_foundation": (
                "revit.create_foundation",
                lambda args: {
                    "family_name": args.get("family_name"),
                    "type_name": args.get("type_name"),
                    "level": args.get("level"),
                    "location": {"x": args.get("x"), "y": args.get("y"), "z": args.get("z", 0)},
                },
            ),
            "revit_create_duct": (
                "revit.create_duct",
                lambda args: {
                    "level": args.get("level"),
                    "start_point": {"x": args.get("start_x"), "y": args.get("start_y"), "z": args.get("z", 10)},
                    "end_point": {"x": args.get("end_x"), "y": args.get("end_y"), "z": args.get("z", 10)},
                    "system_type": args.get("system_type"),
                    "duct_type": args.get("duct_type"),
                },
            ),
            "revit_create_pipe": (
                "revit.create_pipe",
                lambda args: {
                    "level": args.get("level"),
                    "start_point": {"x": args.get("start_x"), "y": args.get("start_y"), "z": args.get("z", 0)},
                    "end_point": {"x": args.get("end_x"), "y": args.get("end_y"), "z": args.get("z", 0)},
                    "system_type": args.get("system_type"),
                    "pipe_type": args.get("pipe_type"),
                },
            ),
            "revit_get_categories": ("revit.get_categories", lambda args: {}),
            "revit_get_element_type": (
                "revit.get_element_type",
                lambda args: {"category_name": args.get("category_name"), "family_name": args.get("family_name")},
            ),
            "revit_close_document": (
                "revit.close_document",
                lambda args: {"save_changes": args.get("save_changes", False)},
            ),
            "revit_create_new_document": (
                "revit.create_new_document",
                lambda args: {"template_path": args.get("template_path")},
            ),
            "revit_export_dwg": (
                "revit.export_dwg_by_view",
                lambda args: {"view_id": args.get("view_id"), "output_path": args.get("output_path")},
            ),
            "revit_export_ifc": (
                "revit.export_ifc_with_settings",
                lambda args: {"output_path": args.get("output_path")},
            ),
            "revit_export_navisworks": (
                "revit.export_navisworks",
                lambda args: {"output_path": args.get("output_path")},
            ),
            "revit_export_image": (
                "revit.export_image",
                lambda args: {
                    "view_id": args.get("view_id"),
                    "output_path": args.get("output_path"),
                    "width": args.get("width"),
                    "height": args.get("height"),
                },
            ),
            "revit_render_3d": (
                "revit.render_3d_view",
                lambda args: {
                    "view_id": args.get("view_id"),
                    "output_path": args.get("output_path"),
                    "quality": args.get("quality", "Medium"),
                },
            ),
            "revit_move_element": (
                "revit.move_element",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "vector": {"x": args.get("x"), "y": args.get("y"), "z": args.get("z", 0)},
                },
            ),
            "revit_copy_element": (
                "revit.copy_element",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "vector": {"x": args.get("x"), "y": args.get("y"), "z": args.get("z", 0)},
                },
            ),
            "revit_rotate_element": (
                "revit.rotate_element",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "axis_point": {"x": args.get("center_x"), "y": args.get("center_y"), "z": args.get("center_z", 0)},
                    "angle_radians": args.get("angle_radians"),
                },
            ),
            "revit_mirror_element": (
                "revit.mirror_element",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "plane_origin": {
                        "x": args.get("plane_origin_x"),
                        "y": args.get("plane_origin_y"),
                        "z": args.get("plane_origin_z", 0),
                    },
                    "plane_normal": {
                        "x": args.get("plane_normal_x"),
                        "y": args.get("plane_normal_y"),
                        "z": args.get("plane_normal_z", 0),
                    },
                },
            ),
            "revit_pin_element": ("revit.pin_element", lambda args: {"element_id": args.get("element_id")}),
            "revit_unpin_element": ("revit.unpin_element", lambda args: {"element_id": args.get("element_id")}),
            "revit_sync_to_central": (
                "revit.sync_to_central",
                lambda args: {
                    "comment": args.get("comment", "Sync via MCP"),
                    "relinquish": args.get("relinquish", True),
                },
            ),
            "revit_relinquish_all": ("revit.relinquish_all", lambda args: {}),
            "revit_get_worksets": ("revit.get_worksets", lambda args: {}),
            "revit_create_schedule": (
                "revit.create_schedule",
                lambda args: {"category_name": args.get("category_name"), "name": args.get("name")},
            ),
            "revit_get_schedule_data": (
                "revit.get_schedule_data",
                lambda args: {"schedule_id": args.get("schedule_id")},
            ),
            "revit_get_element_bounding_box": (
                "revit.get_element_bounding_box",
                lambda args: {"element_id": args.get("element_id")},
            ),
            "revit_get_phases": ("revit.get_phases", lambda args: {}),
            "revit_get_phase_filters": ("revit.get_phase_filters", lambda args: {}),
            "revit_get_design_options": ("revit.get_design_options", lambda args: {}),
            "revit_create_group": (
                "revit.create_group",
                lambda args: {"element_ids": args.get("element_ids"), "name": args.get("name")},
            ),
            "revit_ungroup": ("revit.ungroup", lambda args: {"group_id": args.get("group_id")}),
            "revit_get_group_members": ("revit.get_group_members", lambda args: {"group_id": args.get("group_id")}),
            "revit_get_rvt_links": ("revit.get_rvt_links", lambda args: {}),
            "revit_get_link_instances": ("revit.get_link_instances", lambda args: {}),
            "revit_create_conduit": (
                "revit.create_conduit",
                lambda args: {
                    "level": args.get("level"),
                    "start_point": {"x": args.get("start_x"), "y": args.get("start_y"), "z": args.get("start_z", 10)},
                    "end_point": {"x": args.get("end_x"), "y": args.get("end_y"), "z": args.get("end_z", 10)},
                    "diameter": args.get("diameter", 0.0625),
                    "conduit_type": args.get("conduit_type"),
                },
            ),
            "revit_check_clashes": (
                "revit.check_clashes",
                lambda args: {
                    "category1": args.get("category1"),
                    "category2": args.get("category2"),
                    "tolerance": args.get("tolerance", 0.01),
                },
            ),
            "revit_create_material": (
                "revit.create_material",
                lambda args: {
                    "name": args.get("name"),
                    "color": args.get("color"),
                    "transparency": args.get("transparency", 0),
                    "shininess": args.get("shininess", 50),
                    "smoothness": args.get("smoothness", 50),
                },
            ),
            "revit_set_element_material": (
                "revit.set_element_material",
                lambda args: {
                    "element_id": args.get("element_id"),
                    "material_name": args.get("material_name"),
                    "face_index": args.get("face_index"),
                },
            ),
            "revit_convert_to_group": (
                "revit.convert_to_group",
                lambda args: {"element_ids": args.get("element_ids"), "name": args.get("name")},
            ),
            "revit_edit_family": (
                "revit.edit_family",
                lambda args: {
                    "family_name": args.get("family_name"),
                    "family_symbol_id": args.get("family_symbol_id"),
                    "family_instance_id": args.get("family_instance_id"),
                },
            ),
            "revit_create_dimension": (
                "revit.create_dimension",
                lambda args: {
                    "start_point": args.get("start_point"),
                    "end_point": args.get("end_point"),
                    "element1_id": args.get("element1_id"),
                    "element2_id": args.get("element2_id"),
                },
            ),
            "revit_get_revision_sequences": ("revit.get_revision_sequences", lambda args: {}),
            "revit_tag_all_in_view": ("revit.tag_all_in_view", lambda args: {"category": args.get("category")}),
            "revit_get_view_templates": ("revit.get_view_templates", lambda args: {}),
            "revit_apply_view_template": (
                "revit.apply_view_template",
                lambda args: {"view_id": args.get("view_id"), "template_id": args.get("template_id")},
            ),
            "revit_calculate_material_quantities": (
                "revit.calculate_material_quantities",
                lambda args: {"category": args.get("category")},
            ),
            "revit_get_warnings": ("revit.get_warnings", lambda args: {}),
            "revit_invoke_method": (
                "revit.invoke_method",
                lambda args: {
                    "class_name": args.get("class_name"),
                    "method_name": args.get("method_name"),
                    "arguments": args.get("arguments"),
                    "target_id": args.get("target_id"),
                    "use_transaction": args.get("use_transaction", True),
                },
            ),
            "revit_reflect_get": (
                "revit.reflect_get",
                lambda args: {"target_id": args.get("target_id"), "property_name": args.get("property_name")},
            ),
            "revit_reflect_set": (
                "revit.reflect_set",
                lambda args: {
                    "target_id": args.get("target_id"),
                    "property_name": args.get("property_name"),
                    "value": args.get("value"),
                },
            ),
            "revit_execute_python": ("revit.execute_python", lambda args: {"script": args.get("script")}),
            "revit_change_element_type": (
                "revit.change_element_type",
                lambda args: {
                    "source_type_id": args.get("source_type_id"),
                    "target_type_id": args.get("target_type_id"),
                    "category": args.get("category"),
                },
            ),
            "revit_get_elements_by_type": (
                "revit.get_elements_by_type",
                lambda args: {
                    "type_id": args.get("type_id"),
                    "category": args.get("category"),
                    "level": args.get("level"),
                    "fields": args.get("fields"),
                    "offset": args.get("offset", 0),
                    "limit": args.get("limit", 200),
                },
            ),
            "revit_batch_set_parameters_by_filter": (
                "revit.batch_set_parameters_by_filter",
                lambda args: {
                    "filter": args.get("filter"),
                    "parameter_name": args.get("parameter_name"),
                    "value": args.get("value"),
                },
            ),
            "revit_replace_family_type": (
                "revit.replace_family_type",
                lambda args: {
                    "old_family": args.get("old_family"),
                    "old_type": args.get("old_type"),
                    "new_family": args.get("new_family"),
                    "new_type": args.get("new_type"),
                },
            ),
            "revit_get_element_geometry": (
                "revit.get_element_geometry",
                lambda args: {"element_id": args.get("element_id")},
            ),
            "revit_extract_snapshot": (
                "revit.extract_snapshot",
                lambda args: {"dirty_only": args.get("dirty_only", False)},
            ),
            "revit_get_snapshot_delta": ("revit.get_snapshot_delta", lambda args: {}),
        }

    # Define _capabilities schema list
    _capabilities = [
        ProviderTool(
            name="revit_extract_snapshot",
            description="Extract a semantic BIM snapshot of the active document. Streams to a JSON file in the workspace directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dirty_only": {
                        "type": "boolean",
                        "description": "Extract only added or modified elements tracked in this session",
                        "default": False,
                    }
                },
                "required": [],
            },
        ),
        ProviderTool(
            name="revit_get_snapshot_delta",
            description="Get lists of unique IDs for elements added, modified, or deleted during the active session.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        ProviderTool(
            name="revit_health",
            description="Check if Revit is running and get status information",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        ProviderTool(
            name="revit_create_wall",
            description="Create a wall in Revit between two points",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_x": {"type": "number", "description": "Start point X coordinate in feet"},
                    "start_y": {"type": "number", "description": "Start point Y coordinate in feet"},
                    "start_z": {"type": "number", "description": "Start point Z coordinate in feet", "default": 0},
                    "end_x": {"type": "number", "description": "End point X coordinate in feet"},
                    "end_y": {"type": "number", "description": "End point Y coordinate in feet"},
                    "end_z": {"type": "number", "description": "End point Z coordinate in feet", "default": 0},
                    "height": {"type": "number", "description": "Wall height in feet", "default": 10},
                    "level": {"type": "string", "description": "Level name (e.g., 'L1', 'L2')", "default": "L1"},
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        ),
        ProviderTool(
            name="revit_create_floor",
            description="Create a floor in Revit with a rectangular or custom boundary",
            inputSchema={
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "description": "Array of boundary points [{x, y, z}]. Minimum 3 points for a closed boundary.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "z": {"type": "number", "default": 0},
                            },
                            "required": ["x", "y"],
                        },
                    },
                    "level": {"type": "string", "description": "Level name", "default": "L1"},
                },
                "required": ["points"],
            },
        ),
        ProviderTool(
            name="revit_create_roof",
            description="Create a roof in Revit",
            inputSchema={
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "description": "Array of boundary points for the roof",
                        "items": {
                            "type": "object",
                            "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
                        },
                    },
                    "level": {"type": "string", "description": "Level name"},
                    "slope": {"type": "number", "description": "Roof slope", "default": 0.5},
                },
                "required": ["points", "level"],
            },
        ),
        ProviderTool(
            name="revit_list_levels",
            description="List all levels in the Revit project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        ProviderTool(
            name="revit_list_views",
            description="List all views in the Revit project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        ProviderTool(
            name="revit_list_elements",
            description="List elements by category (Walls, Floors, Roofs, Doors, Windows, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category name (e.g., 'Walls', 'Floors', 'Doors')"}
                },
                "required": ["category"],
            },
        ),
        ProviderTool(
            name="revit_get_document_info",
            description="Get information about the active Revit document",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        ProviderTool(
            name="revit_create_level",
            description="Create a new level in Revit",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Level name"},
                    "elevation": {"type": "number", "description": "Elevation in feet"},
                },
                "required": ["name", "elevation"],
            },
        ),
        ProviderTool(
            name="revit_save_document",
            description="Save the current Revit document",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to save to (optional for existing files)"}
                },
            },
        ),
        ProviderTool(
            name="revit_create_grid",
            description="Create a grid line in Revit",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_x": {"type": "number"},
                    "start_y": {"type": "number"},
                    "start_z": {"type": "number", "default": 0},
                    "end_x": {"type": "number"},
                    "end_y": {"type": "number"},
                    "end_z": {"type": "number", "default": 0},
                    "name": {"type": "string"},
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        ),
        ProviderTool(
            name="revit_create_room",
            description="Create a room at a specific point on a level",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "name": {"type": "string", "default": "Room"},
                    "number": {"type": "string"},
                },
                "required": ["level", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_delete_element",
            description="Delete an element by ID",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}},
                "required": ["element_id"],
            },
        ),
        ProviderTool(
            name="revit_place_family_instance",
            description="Place a family instance (e.g., furniture, equipment)",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_name": {"type": "string"},
                    "type_name": {"type": "string"},
                    "level": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number", "default": 0},
                },
                "required": ["family_name", "type_name", "level", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_place_door",
            description="Place a door in a wall",
            inputSchema={
                "type": "object",
                "properties": {
                    "wall_id": {"type": "integer"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number", "default": 0},
                    "location": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number", "default": 0},
                        },
                        "required": ["x", "y"],
                    },
                    "family_name": {"type": "string"},
                    "type_name": {"type": "string"},
                },
                "required": ["wall_id"],
                "oneOf": [{"required": ["x", "y"]}, {"required": ["location"]}],
            },
        ),
        ProviderTool(
            name="revit_place_window",
            description="Place a window in a wall",
            inputSchema={
                "type": "object",
                "properties": {
                    "wall_id": {"type": "integer"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number", "default": 0},
                    "location": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number", "default": 0},
                        },
                        "required": ["x", "y"],
                    },
                    "family_name": {"type": "string"},
                    "type_name": {"type": "string"},
                },
                "required": ["wall_id"],
                "oneOf": [{"required": ["x", "y"]}, {"required": ["location"]}],
            },
        ),
        ProviderTool(
            name="revit_list_families",
            description="List all loaded families and their types",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_create_floor_plan_view",
            description="Create a floor plan view for a level",
            inputSchema={
                "type": "object",
                "properties": {"level_name": {"type": "string"}, "view_name": {"type": "string"}},
                "required": ["level_name"],
            },
        ),
        ProviderTool(
            name="revit_create_3d_view",
            description="Create a new 3D view",
            inputSchema={"type": "object", "properties": {"view_name": {"type": "string"}}, "required": ["view_name"]},
        ),
        ProviderTool(
            name="revit_create_section_view",
            description="Create a section view",
            inputSchema={
                "type": "object",
                "properties": {
                    "view_name": {"type": "string"},
                    "start_x": {"type": "number"},
                    "start_y": {"type": "number"},
                    "start_z": {"type": "number"},
                    "end_x": {"type": "number"},
                    "end_y": {"type": "number"},
                    "end_z": {"type": "number"},
                    "height": {"type": "number", "default": 10},
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        ),
        ProviderTool(
            name="revit_get_element_parameters",
            description="Get all parameters of an element",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}},
                "required": ["element_id"],
            },
        ),
        ProviderTool(
            name="revit_set_parameter_value",
            description="Set a parameter value for an element",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "parameter_name": {"type": "string"},
                    "value": {"type": ["string", "number", "boolean"]},
                },
                "required": ["element_id", "parameter_name", "value"],
            },
        ),
        ProviderTool(
            name="revit_get_parameter_value",
            description="Get a specific parameter value",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}, "parameter_name": {"type": "string"}},
                "required": ["element_id", "parameter_name"],
            },
        ),
        ProviderTool(
            name="revit_list_shared_parameters",
            description="List shared parameters in the document",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_create_shared_parameter",
            description="Create a new shared parameter",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "group": {"type": "string"},
                    "type": {"type": "string"},
                    "visible": {"type": "boolean"},
                },
                "required": ["name"],
            },
        ),
        ProviderTool(
            name="revit_list_project_parameters",
            description="List project parameters",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_create_project_parameter",
            description="Create a new project parameter",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "group": {"type": "string"},
                    "type": {"type": "string"},
                },
                "required": ["name", "category"],
            },
        ),
        ProviderTool(
            name="revit_batch_set_parameters",
            description="Set a parameter value for multiple elements",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_ids": {"type": "array", "items": {"type": "integer"}},
                    "parameter_name": {"type": "string"},
                    "value": {"type": ["string", "number"]},
                },
                "required": ["element_ids", "parameter_name", "value"],
            },
        ),
        ProviderTool(
            name="revit_get_type_parameters",
            description="Get type parameters for an element",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}},
                "required": ["element_id"],
            },
        ),
        ProviderTool(
            name="revit_set_type_parameter",
            description="Set a type parameter value",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "parameter_name": {"type": "string"},
                    "value": {"type": ["string", "number"]},
                },
                "required": ["element_id", "parameter_name", "value"],
            },
        ),
        ProviderTool(
            name="revit_list_sheets", description="List all sheets", inputSchema={"type": "object", "properties": {}}
        ),
        ProviderTool(
            name="revit_create_sheet",
            description="Create a new sheet",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "number": {"type": "string"},
                    "titleblock_id": {"type": "integer"},
                },
                "required": ["name", "number"],
            },
        ),
        ProviderTool(
            name="revit_delete_sheet",
            description="Delete a sheet",
            inputSchema={"type": "object", "properties": {"sheet_id": {"type": "integer"}}, "required": ["sheet_id"]},
        ),
        ProviderTool(
            name="revit_place_viewport_on_sheet",
            description="Place a view on a sheet",
            inputSchema={
                "type": "object",
                "properties": {
                    "sheet_id": {"type": "integer"},
                    "view_id": {"type": "integer"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                },
                "required": ["sheet_id", "view_id", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_batch_create_sheets_from_csv",
            description="Create multiple sheets from a CSV file",
            inputSchema={
                "type": "object",
                "properties": {"csv_path": {"type": "string"}, "titleblock_name": {"type": "string"}},
                "required": ["csv_path"],
            },
        ),
        ProviderTool(
            name="revit_populate_titleblock",
            description="Populate titleblock parameters",
            inputSchema={
                "type": "object",
                "properties": {"sheet_id": {"type": "integer"}, "parameters": {"type": "object"}},
                "required": ["sheet_id", "parameters"],
            },
        ),
        ProviderTool(
            name="revit_list_titleblocks",
            description="List available titleblocks",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_get_sheet_info",
            description="Get detailed information about a sheet",
            inputSchema={"type": "object", "properties": {"sheet_id": {"type": "integer"}}, "required": ["sheet_id"]},
        ),
        ProviderTool(
            name="revit_duplicate_sheet",
            description="Duplicate a sheet",
            inputSchema={
                "type": "object",
                "properties": {
                    "sheet_id": {"type": "integer"},
                    "with_views": {"type": "boolean"},
                    "duplicate_option": {"type": "string"},
                },
                "required": ["sheet_id"],
            },
        ),
        ProviderTool(
            name="revit_renumber_sheets",
            description="Batch renumber sheets",
            inputSchema={
                "type": "object",
                "properties": {"prefix": {"type": "string"}, "start_number": {"type": "integer"}},
                "required": ["start_number"],
            },
        ),
        ProviderTool(
            name="revit_get_selection",
            description="Get currently selected element IDs",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_set_selection",
            description="Set selection by element IDs",
            inputSchema={
                "type": "object",
                "properties": {"element_ids": {"type": "array", "items": {"type": "integer"}}},
                "required": ["element_ids"],
            },
        ),
        # Not flagged mutating: only changes what's selected/framed in the active
        # view, never the document, so the dockable panel can jump to a flagged
        # element (by its stable UniqueId, unlike revit_set_selection's
        # session-scoped ElementIds) without an approval round trip.
        ProviderTool(
            name="revit_select_by_unique_ids",
            description="Select and zoom to elements in the active view by their UniqueId",
            inputSchema={
                "type": "object",
                "properties": {"element_uids": {"type": "array", "items": {"type": "string"}}},
                "required": ["element_uids"],
            },
        ),
        ProviderTool(
            name="revit_create_text_note",
            description="Create a text note",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "view_id": {"type": "integer"},
                },
                "required": ["text", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_create_tag",
            description="Tag an element",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "view_id": {"type": "integer"},
                },
                "required": ["element_id", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_create_column",
            description="Create structural column",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_name": {"type": "string"},
                    "type_name": {"type": "string"},
                    "level": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                },
                "required": ["family_name", "type_name", "level", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_create_beam",
            description="Create structural beam",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_name": {"type": "string"},
                    "type_name": {"type": "string"},
                    "level": {"type": "string"},
                    "start_x": {"type": "number"},
                    "start_y": {"type": "number"},
                    "end_x": {"type": "number"},
                    "end_y": {"type": "number"},
                },
                "required": ["family_name", "type_name", "level", "start_x", "start_y", "end_x", "end_y"],
            },
        ),
        ProviderTool(
            name="revit_create_foundation",
            description="Create foundation",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_name": {"type": "string"},
                    "type_name": {"type": "string"},
                    "level": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number", "default": 0},
                },
                "required": ["family_name", "type_name", "level", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_create_duct",
            description="Create duct",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string"},
                    "start_x": {"type": "number"},
                    "start_y": {"type": "number"},
                    "end_x": {"type": "number"},
                    "end_y": {"type": "number"},
                    "z": {"type": "number", "default": 10},
                    "system_type": {"type": "string"},
                    "duct_type": {"type": "string"},
                },
                "required": ["level", "start_x", "start_y", "end_x", "end_y"],
            },
        ),
        ProviderTool(
            name="revit_create_pipe",
            description="Create pipe",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string"},
                    "start_x": {"type": "number"},
                    "start_y": {"type": "number"},
                    "end_x": {"type": "number"},
                    "end_y": {"type": "number"},
                    "z": {"type": "number", "default": 0},
                    "system_type": {"type": "string"},
                    "pipe_type": {"type": "string"},
                },
                "required": ["level", "start_x", "start_y", "end_x", "end_y"],
            },
        ),
        ProviderTool(
            name="revit_get_categories",
            description="List Revit categories",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_get_element_type",
            description="Find element types/families",
            inputSchema={
                "type": "object",
                "properties": {"category_name": {"type": "string"}, "family_name": {"type": "string"}},
                "required": ["category_name"],
            },
        ),
        ProviderTool(
            name="revit_close_document",
            description="Close active document",
            inputSchema={"type": "object", "properties": {"save_changes": {"type": "boolean", "default": False}}},
        ),
        ProviderTool(
            name="revit_create_new_document",
            description="Create new project",
            inputSchema={"type": "object", "properties": {"template_path": {"type": "string"}}},
        ),
        ProviderTool(
            name="revit_export_dwg",
            description="Export view to DWG",
            inputSchema={
                "type": "object",
                "properties": {"view_id": {"type": "integer"}, "output_path": {"type": "string"}},
                "required": ["view_id", "output_path"],
            },
        ),
        ProviderTool(
            name="revit_export_ifc",
            description="Export to IFC",
            inputSchema={
                "type": "object",
                "properties": {"output_path": {"type": "string"}},
                "required": ["output_path"],
            },
        ),
        ProviderTool(
            name="revit_export_navisworks",
            description="Export to NWC",
            inputSchema={
                "type": "object",
                "properties": {"output_path": {"type": "string"}},
                "required": ["output_path"],
            },
        ),
        ProviderTool(
            name="revit_export_image",
            description="Export view to Image",
            inputSchema={
                "type": "object",
                "properties": {
                    "view_id": {"type": "integer"},
                    "output_path": {"type": "string"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                },
                "required": ["view_id", "output_path"],
            },
        ),
        ProviderTool(
            name="revit_render_3d",
            description="Render 3D view to image",
            inputSchema={
                "type": "object",
                "properties": {
                    "view_id": {"type": "integer"},
                    "output_path": {"type": "string"},
                    "quality": {"type": "string", "enum": ["Draft", "Medium", "High"]},
                },
                "required": ["view_id", "output_path"],
            },
        ),
        ProviderTool(
            name="revit_move_element",
            description="Move an element",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number", "default": 0},
                },
                "required": ["element_id", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_copy_element",
            description="Copy an element",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number", "default": 0},
                },
                "required": ["element_id", "x", "y"],
            },
        ),
        ProviderTool(
            name="revit_rotate_element",
            description="Rotate an element",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "center_x": {"type": "number"},
                    "center_y": {"type": "number"},
                    "center_z": {"type": "number", "default": 0},
                    "angle_radians": {"type": "number"},
                },
                "required": ["element_id", "center_x", "center_y", "angle_radians"],
            },
        ),
        ProviderTool(
            name="revit_mirror_element",
            description="Mirror an element",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "plane_origin_x": {"type": "number"},
                    "plane_origin_y": {"type": "number"},
                    "plane_origin_z": {"type": "number", "default": 0},
                    "plane_normal_x": {"type": "number"},
                    "plane_normal_y": {"type": "number"},
                    "plane_normal_z": {"type": "number", "default": 0},
                },
                "required": ["element_id", "plane_origin_x", "plane_origin_y", "plane_normal_x", "plane_normal_y"],
            },
        ),
        ProviderTool(
            name="revit_pin_element",
            description="Pin an element",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}},
                "required": ["element_id"],
            },
        ),
        ProviderTool(
            name="revit_unpin_element",
            description="Unpin an element",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}},
                "required": ["element_id"],
            },
        ),
        ProviderTool(
            name="revit_sync_to_central",
            description="Sync to central model",
            inputSchema={
                "type": "object",
                "properties": {"comment": {"type": "string"}, "relinquish": {"type": "boolean", "default": True}},
            },
        ),
        ProviderTool(
            name="revit_relinquish_all",
            description="Relinquish all elements and worksets",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_get_worksets", description="Get all worksets", inputSchema={"type": "object", "properties": {}}
        ),
        ProviderTool(
            name="revit_create_schedule",
            description="Create a schedule",
            inputSchema={
                "type": "object",
                "properties": {"category_name": {"type": "string"}, "name": {"type": "string"}},
                "required": ["category_name", "name"],
            },
        ),
        ProviderTool(
            name="revit_get_schedule_data",
            description="Get schedule data",
            inputSchema={
                "type": "object",
                "properties": {"schedule_id": {"type": "integer"}},
                "required": ["schedule_id"],
            },
        ),
        ProviderTool(
            name="revit_get_element_bounding_box",
            description="Get element bounding box",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}},
                "required": ["element_id"],
            },
        ),
        ProviderTool(
            name="revit_get_phases", description="Get project phases", inputSchema={"type": "object", "properties": {}}
        ),
        ProviderTool(
            name="revit_get_phase_filters",
            description="Get phase filters",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_get_design_options",
            description="Get design options",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_create_group",
            description="Create a group",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_ids": {"type": "array", "items": {"type": "integer"}},
                    "name": {"type": "string"},
                },
                "required": ["element_ids", "name"],
            },
        ),
        ProviderTool(
            name="revit_ungroup",
            description="Ungroup a group",
            inputSchema={"type": "object", "properties": {"group_id": {"type": "integer"}}, "required": ["group_id"]},
        ),
        ProviderTool(
            name="revit_get_group_members",
            description="Get group members",
            inputSchema={"type": "object", "properties": {"group_id": {"type": "integer"}}, "required": ["group_id"]},
        ),
        ProviderTool(
            name="revit_get_rvt_links", description="Get RVT links", inputSchema={"type": "object", "properties": {}}
        ),
        ProviderTool(
            name="revit_get_link_instances",
            description="Get link instances",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_create_conduit",
            description="Create electrical conduit",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string"},
                    "start_x": {"type": "number"},
                    "start_y": {"type": "number"},
                    "start_z": {"type": "number", "default": 10},
                    "end_x": {"type": "number"},
                    "end_y": {"type": "number"},
                    "end_z": {"type": "number", "default": 10},
                    "diameter": {"type": "number", "default": 0.0625},
                },
                "required": ["level", "start_x", "start_y", "end_x", "end_y"],
            },
        ),
        ProviderTool(
            name="revit_check_clashes",
            description="Check clashes between categories",
            inputSchema={
                "type": "object",
                "properties": {
                    "category1": {"type": "string"},
                    "category2": {"type": "string"},
                    "tolerance": {"type": "number", "default": 0.01},
                },
                "required": ["category1", "category2"],
            },
        ),
        ProviderTool(
            name="revit_create_material",
            description="Create a new material with color and properties",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "color": {
                        "type": "object",
                        "properties": {"r": {"type": "integer"}, "g": {"type": "integer"}, "b": {"type": "integer"}},
                    },
                    "transparency": {"type": "integer", "default": 0},
                    "shininess": {"type": "integer", "default": 50},
                    "smoothness": {"type": "integer", "default": 50},
                },
                "required": ["name"],
            },
        ),
        ProviderTool(
            name="revit_set_element_material",
            description="Set material for an element or specific face",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "material_name": {"type": "string"},
                    "face_index": {"type": "integer", "description": "Optional face index for face-specific material"},
                },
                "required": ["element_id", "material_name"],
            },
        ),
        ProviderTool(
            name="revit_convert_to_group",
            description="Convert elements into a group",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_ids": {"type": "array", "items": {"type": "integer"}},
                    "name": {"type": "string"},
                },
                "required": ["element_ids"],
            },
        ),
        ProviderTool(
            name="revit_edit_family",
            description="Open a family for editing",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_name": {"type": "string"},
                    "family_symbol_id": {"type": "integer"},
                    "family_instance_id": {"type": "integer"},
                },
                "required": [],
            },
        ),
        ProviderTool(
            name="revit_create_dimension",
            description="Create linear dimension between elements",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_point": {
                        "type": "object",
                        "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
                    },
                    "end_point": {
                        "type": "object",
                        "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
                    },
                    "element1_id": {"type": "integer"},
                    "element2_id": {"type": "integer"},
                },
                "required": ["start_point", "end_point", "element1_id", "element2_id"],
            },
        ),
        ProviderTool(
            name="revit_get_revision_sequences",
            description="Get list of revision sequences",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_tag_all_in_view",
            description="Tag all elements of a category in view",
            inputSchema={"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]},
        ),
        ProviderTool(
            name="revit_get_view_templates",
            description="Get list of view templates",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_apply_view_template",
            description="Apply view template to a view",
            inputSchema={
                "type": "object",
                "properties": {"view_id": {"type": "integer"}, "template_id": {"type": "integer"}},
                "required": ["view_id", "template_id"],
            },
        ),
        ProviderTool(
            name="revit_calculate_material_quantities",
            description="Calculate material volumes for a category",
            inputSchema={"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]},
        ),
        ProviderTool(
            name="revit_get_warnings",
            description="Get current project warnings",
            inputSchema={"type": "object", "properties": {}},
        ),
        ProviderTool(
            name="revit_invoke_method",
            description="Invoke any Revit API method dynamically using Reflection",
            inputSchema={
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "method_name": {"type": "string"},
                    "arguments": {"type": "array", "items": {}},
                    "target_id": {"type": "string"},
                    "use_transaction": {"type": "boolean", "default": True},
                },
                "required": ["class_name", "method_name", "arguments"],
            },
        ),
        ProviderTool(
            name="revit_reflect_get",
            description="Get any Revit property value dynamically",
            inputSchema={
                "type": "object",
                "properties": {"target_id": {"type": "string"}, "property_name": {"type": "string"}},
                "required": ["target_id", "property_name"],
            },
        ),
        ProviderTool(
            name="revit_reflect_set",
            description="Set any Revit property value dynamically",
            inputSchema={
                "type": "object",
                "properties": {"target_id": {"type": "string"}, "property_name": {"type": "string"}, "value": {}},
                "required": ["target_id", "property_name", "value"],
            },
        ),
        ProviderTool(
            name="revit_execute_python",
            description="Execute arbitrary Python/IronPython code inside Revit with broad access to the public Revit API.",
            inputSchema={
                "type": "object",
                "properties": {"script": {"type": "string", "description": "Python script to execute"}},
                "required": ["script"],
            },
        ),
        ProviderTool(
            name="revit_change_element_type",
            description="Swap all instances of one element type to another type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_type_id": {"type": "integer", "description": "Element type ID to replace (all instances)"},
                    "target_type_id": {"type": "integer", "description": "Element type ID to change to"},
                    "category": {
                        "type": "string",
                        "description": "Optional category filter (e.g. 'Walls', 'Doors') to limit scope",
                    },
                },
                "required": ["source_type_id", "target_type_id"],
            },
        ),
        ProviderTool(
            name="revit_get_elements_by_type",
            description="Get element IDs and key parameters, filtered by type, category, and/or level.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type_id": {"type": "integer", "description": "Filter by element type ID (optional)"},
                    "category": {
                        "type": "string",
                        "description": "Filter by category name, e.g. 'Walls', 'Doors' (optional)",
                    },
                    "level": {"type": "string", "description": "Filter by level name, e.g. 'BG', 'L1' (optional)"},
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to return: id always included. Options: name, category, type_id, level, length, area, volume",
                    },
                    "offset": {"type": "integer", "description": "Pagination offset (default 0)", "default": 0},
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 200, max 500)",
                        "default": 200,
                    },
                },
                "required": [],
            },
        ),
        ProviderTool(
            name="revit_batch_set_parameters_by_filter",
            description="Set a parameter value on all elements matching a filter (category, type, level, or parameter value).",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "object",
                        "description": "Filter criteria to select elements",
                        "properties": {
                            "category": {"type": "string", "description": "Category name, e.g. 'Walls'"},
                            "type_id": {"type": "integer", "description": "Element type ID filter"},
                            "level": {"type": "string", "description": "Level name filter"},
                            "parameter_filter": {
                                "type": "object",
                                "description": "Only include elements where this parameter equals this value",
                                "properties": {"name": {"type": "string"}, "value": {}},
                                "required": ["name", "value"],
                            },
                        },
                    },
                    "parameter_name": {"type": "string", "description": "Name of the parameter to set"},
                    "value": {"description": "Value to set (string, number, or boolean)"},
                },
                "required": ["filter", "parameter_name", "value"],
            },
        ),
        ProviderTool(
            name="revit_replace_family_type",
            description="Replace all instances of one family/type combination with another, identified by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "old_family": {
                        "type": "string",
                        "description": "Current family name (exact match, case-insensitive)",
                    },
                    "old_type": {"type": "string", "description": "Current type name"},
                    "new_family": {"type": "string", "description": "Replacement family name"},
                    "new_type": {"type": "string", "description": "Replacement type name"},
                },
                "required": ["old_family", "old_type", "new_family", "new_type"],
            },
        ),
        ProviderTool(
            name="revit_get_element_geometry",
            description="Get geometric data for an element: location point or curve endpoints, bounding box, level, area, volume, and length.",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer", "description": "Element ID"}},
                "required": ["element_id"],
            },
        ),
    ]

    async def shutdown(self) -> None:
        close = getattr(getattr(self, "_bridge", None), "close", None)
        if callable(close):
            close()
