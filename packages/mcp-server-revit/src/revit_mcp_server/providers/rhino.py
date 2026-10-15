import logging
from typing import Any, Dict, List

from ..config import config, BridgeMode
from ..bridge.client import BridgeClient
from ..security.workspace import WorkspaceMonitor
from .base import AECProvider, ProviderTool, enrich_mutation_metadata

logger = logging.getLogger(__name__)


def _optional(args: Dict, *keys) -> Dict:
    """Return a dict of only the keys present in args (used to build sparse bridge payloads)."""
    return {k: args[k] for k in keys if k in args}


class RhinoProvider(AECProvider):
    def __init__(
        self,
        workspace: WorkspaceMonitor,
        mode: BridgeMode = config.mode,
        bridge_url: str | None = None,
        bridge_factory=None
    ) -> None:
        self.workspace = workspace
        self.mode = mode
        
        url = bridge_url or "http://127.0.0.1:3004"
        bridge_factory = bridge_factory or (lambda u, t=None: BridgeClient(u, token=t))
        self._bridge = bridge_factory(url, None)
        self._init_tool_mapping()
        self._enrich_tool_metadata()

    def _enrich_tool_metadata(self) -> None:
        # rhino_run_python executes arbitrary IronPython with full RhinoCommon access —
        # same escape-hatch risk class as revit_execute_python, so it gets the same
        # mutating+destructive treatment. reflect_get/invoke_method/reflect_set are
        # left at the same risk level revit.py uses for their Revit-side equivalents
        # (mutating via the "invoke"/"set" verbs, not separately marked destructive).
        mutating_verbs = {"create", "clear", "set", "transform", "run", "boolean", "invoke"}
        enrich_mutation_metadata(self._capabilities, mutating_verbs=mutating_verbs, destructive={"rhino_run_python"})

    def get_identity(self) -> str:
        return "rhino"

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        if self.mode == BridgeMode.bridge:
            try:
                if hasattr(self._bridge, '_get'):
                    return self._bridge._get("/health")
                return {"status": "healthy", "mode": "bridge"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}
        return {"status": "healthy", "mode": "mock"}

    async def shutdown(self) -> None:
        close = getattr(getattr(self, "_bridge", None), "close", None)
        if callable(close):
            close()

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tool_mapping:
            raise ValueError(f"Unknown Rhino tool '{name}'")
            
        bridge_tool, payload_builder = self._tool_mapping[name]
        payload = payload_builder(arguments)
        
        if "request_id" in arguments and "request_id" not in payload:
            payload["request_id"] = arguments["request_id"]

        if self.mode == BridgeMode.bridge:
            return self._bridge.send_tool(bridge_tool, payload)
        else:
            return {"mock": True, "tool": bridge_tool, "payload": payload}

    def _init_tool_mapping(self):
        self._tool_mapping = {
            # ── Core ──────────────────────────────────────────────────────────────
            "rhino_health": ("health", lambda args: {}),
            "rhino_get_document_info": ("get_document_info", lambda args: {}),
            "rhino_get_lines": ("get_lines", lambda args: {}),
            # ── Scene ─────────────────────────────────────────────────────────────
            "rhino_get_scene": ("get_scene", lambda args: {}),
            "rhino_list_layers": ("list_layers", lambda args: {}),
            "rhino_clear_scene": ("clear_scene", lambda args: {
                **({"layer": args["layer"]} if "layer" in args else {})
            }),
            "rhino_set_view": ("set_view", lambda args: {
                "view": args.get("view", "perspective")
            }),
            # ── Geometry creation ─────────────────────────────────────────────────
            "rhino_create_box": ("create_box", lambda args: {
                "min_pt": args["min_pt"],
                "max_pt": args["max_pt"],
                **_optional(args, "layer", "color"),
            }),
            "rhino_create_sphere": ("create_sphere", lambda args: {
                "center": args["center"],
                "radius": args["radius"],
                **_optional(args, "layer", "color"),
            }),
            "rhino_create_cylinder": ("create_cylinder", lambda args: {
                "base": args["base"],
                "height": args["height"],
                "radius": args["radius"],
                **_optional(args, "layer", "color"),
            }),
            # ── Booleans ──────────────────────────────────────────────────────────
            "rhino_boolean_union": ("boolean_union", lambda args: {
                "ids": args["ids"],
                **_optional(args, "layer"),
            }),
            "rhino_boolean_difference": ("boolean_difference", lambda args: {
                "base_id": args["base_id"],
                "cutter_ids": args["cutter_ids"],
            }),
            # ── Materials ─────────────────────────────────────────────────────────
            "rhino_set_material": ("set_material", lambda args: {
                **_optional(args, "ids", "layer", "color", "transparency",
                            "reflectivity", "name"),
            }),
            # ── Transform ─────────────────────────────────────────────────────────
            "rhino_transform_objects": ("transform_objects", lambda args: {
                "ids": args["ids"],
                **_optional(args, "translation", "rotation", "scale"),
            }),
            # ── Python execution ──────────────────────────────────────────────────
            "rhino_run_python": ("run_python", lambda args: {
                "code": args["code"]
            }),
            # ── Parametric tower ──────────────────────────────────────────────────
            "rhino_generate_diagrid_tower": ("generate_diagrid_tower", lambda args: {
                "base_radius":      args.get("base_radius",      22.0),
                "waist_radius":     args.get("waist_radius",     14.0),
                "top_radius":       args.get("top_radius",       19.0),
                "height":           args.get("height",          180.0),
                "u_divs":           args.get("u_divs",             16),
                "v_divs":           args.get("v_divs",             28),
                "mullion_width":    args.get("mullion_width",    0.15),
                "mullion_depth":    args.get("mullion_depth",    0.30),
                "glass_thickness":  args.get("glass_thickness", 0.024),
                "inset_ratio":      args.get("inset_ratio",     0.12),
            }),
            # ── Reflection ────────────────────────────────────────────────────────
            "rhino_invoke_method": ("invoke_method", lambda args: {
                "class_name":  args.get("class_name"),
                "method_name": args.get("method_name"),
                "arguments":   args.get("arguments"),
                "target_id":   args.get("target_id"),
            }),
            "rhino_reflect_get": ("reflect_get", lambda args: {
                "target_id":     args.get("target_id"),
                "property_name": args.get("property_name"),
            }),
            "rhino_reflect_set": ("reflect_set", lambda args: {
                "target_id":     args.get("target_id"),
                "property_name": args.get("property_name"),
                "value":         args.get("value"),
            }),
        }

    _capabilities = [
        ProviderTool(
            name="rhino_health",
            description="Check if the Rhino bridge is running and healthy",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        ProviderTool(
            name="rhino_get_document_info",
            description="Get the active Rhino document name, path, unit system, and object count",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        ProviderTool(
            name="rhino_get_lines",
            description="Get all curves/lines from the active Rhino document",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        ProviderTool(
            name="rhino_get_scene",
            description="Get all objects in the Rhino scene with their type, layer, and bounding box",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        ProviderTool(
            name="rhino_list_layers",
            description="List all layers in the Rhino document with name, color, visibility, and lock state",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        ProviderTool(
            name="rhino_clear_scene",
            description="Delete all objects in the Rhino document, or only objects on a specific layer",
            inputSchema={"type": "object", "properties": {
                "layer": {"type": "string", "description": "Optional layer name; omit to delete everything"}
            }, "required": []}
        ),
        ProviderTool(
            name="rhino_set_view",
            description="Set the active Rhino viewport display mode or projection",
            inputSchema={"type": "object", "properties": {
                "view": {"type": "string",
                         "enum": ["perspective", "top", "front", "right", "rendered", "arctic"],
                         "description": "Viewport to switch to"}
            }, "required": ["view"]}
        ),
        ProviderTool(
            name="rhino_create_box",
            description="Create a box (rectangular prism) from two corner points in metres",
            inputSchema={"type": "object", "properties": {
                "min_pt": {"type": "array", "items": {"type": "number"}, "description": "[x,y,z] min corner"},
                "max_pt": {"type": "array", "items": {"type": "number"}, "description": "[x,y,z] max corner"},
                "layer":  {"type": "string"},
                "color":  {"type": "array", "items": {"type": "integer"}, "description": "[r,g,b]"},
            }, "required": ["min_pt", "max_pt"]}
        ),
        ProviderTool(
            name="rhino_create_sphere",
            description="Create a sphere by centre point and radius in metres",
            inputSchema={"type": "object", "properties": {
                "center": {"type": "array", "items": {"type": "number"}, "description": "[x,y,z]"},
                "radius": {"type": "number"},
                "layer":  {"type": "string"},
                "color":  {"type": "array", "items": {"type": "integer"}},
            }, "required": ["center", "radius"]}
        ),
        ProviderTool(
            name="rhino_create_cylinder",
            description="Create a capped cylinder from base point, height, and radius in metres",
            inputSchema={"type": "object", "properties": {
                "base":   {"type": "array", "items": {"type": "number"}, "description": "[x,y,z] base centre"},
                "height": {"type": "number"},
                "radius": {"type": "number"},
                "layer":  {"type": "string"},
                "color":  {"type": "array", "items": {"type": "integer"}},
            }, "required": ["base", "height", "radius"]}
        ),
        ProviderTool(
            name="rhino_boolean_union",
            description="Boolean union a list of Brep objects by GUID; returns new object GUIDs",
            inputSchema={"type": "object", "properties": {
                "ids":   {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to union"},
                "layer": {"type": "string"},
            }, "required": ["ids"]}
        ),
        ProviderTool(
            name="rhino_boolean_difference",
            description="Subtract cutter Breps from a base Brep; returns new object GUIDs",
            inputSchema={"type": "object", "properties": {
                "base_id":     {"type": "string"},
                "cutter_ids":  {"type": "array", "items": {"type": "string"}},
            }, "required": ["base_id", "cutter_ids"]}
        ),
        ProviderTool(
            name="rhino_set_material",
            description="Apply a material to objects by GUID list or by layer name",
            inputSchema={"type": "object", "properties": {
                "ids":          {"type": "array", "items": {"type": "string"}},
                "layer":        {"type": "string"},
                "color":        {"type": "array", "items": {"type": "integer"}, "description": "[r,g,b]"},
                "transparency": {"type": "number", "minimum": 0, "maximum": 1},
                "reflectivity": {"type": "number", "minimum": 0, "maximum": 1},
                "name":         {"type": "string"},
            }, "required": []}
        ),
        ProviderTool(
            name="rhino_transform_objects",
            description="Move, rotate, or scale objects by GUID. Provide exactly one of: translation, rotation, or scale",
            inputSchema={"type": "object", "properties": {
                "ids":         {"type": "array", "items": {"type": "string"}},
                "translation": {"type": "array", "items": {"type": "number"}, "description": "[dx,dy,dz] in metres"},
                "rotation":    {"type": "object", "properties": {
                    "axis":      {"type": "array", "items": {"type": "number"}},
                    "angle_deg": {"type": "number"},
                    "origin":    {"type": "array", "items": {"type": "number"}},
                }},
                "scale":       {"type": "array", "items": {"type": "number"}, "description": "[sx,sy,sz]"},
            }, "required": ["ids"]}
        ),
        ProviderTool(
            name="rhino_run_python",
            description="Execute arbitrary IronPython code inside Rhino with full RhinoCommon access. stdout is captured and returned.",
            inputSchema={"type": "object", "properties": {
                "code": {"type": "string", "description": "Python source code to run inside Rhino"},
            }, "required": ["code"]}
        ),
        ProviderTool(
            name="rhino_generate_diagrid_tower",
            description="Generate a parametric diagrid skyscraper with aluminum mullion sweeps and glass panel solids. All dims in metres.",
            inputSchema={"type": "object", "properties": {
                "base_radius":     {"type": "number", "description": "Ground floor radius (m)"},
                "waist_radius":    {"type": "number", "description": "Narrowest radius at mid-height (m)"},
                "top_radius":      {"type": "number", "description": "Crown radius (m)"},
                "height":          {"type": "number", "description": "Total tower height (m)"},
                "u_divs":          {"type": "integer", "description": "Panels around circumference"},
                "v_divs":          {"type": "integer", "description": "Panels up the height"},
                "mullion_width":   {"type": "number", "description": "Visible face width (m)"},
                "mullion_depth":   {"type": "number", "description": "Structural depth toward exterior (m)"},
                "glass_thickness": {"type": "number", "description": "IGU depth (m)"},
                "inset_ratio":     {"type": "number", "description": "Fraction to inset glass corners from cell edge"},
            }, "required": []}
        ),
        ProviderTool(
            name="rhino_invoke_method",
            description="Invoke a C# method on a Rhino object via reflection",
            inputSchema={"type": "object", "properties": {
                "class_name":  {"type": "string"},
                "method_name": {"type": "string"},
                "arguments":   {"type": "array"},
                "target_id":   {"type": "string"},
            }, "required": ["class_name", "method_name", "arguments"]}
        ),
        ProviderTool(
            name="rhino_reflect_get",
            description="Get a C# property value from a Rhino object via reflection",
            inputSchema={"type": "object", "properties": {
                "target_id":     {"type": "string"},
                "property_name": {"type": "string"},
            }, "required": ["target_id", "property_name"]}
        ),
        ProviderTool(
            name="rhino_reflect_set",
            description="Set a C# property value on a Rhino object via reflection",
            inputSchema={"type": "object", "properties": {
                "target_id":     {"type": "string"},
                "property_name": {"type": "string"},
                "value":         {},
            }, "required": ["target_id", "property_name", "value"]}
        ),
    ]
