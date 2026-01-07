"""
MCP Server for Revit - Enables Claude Desktop to control Revit through natural language.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .bridge.client import BridgeClient
from .config import config
from .errors import BridgeError

# Initialize the MCP server
app = Server("revit-mcp")

# Initialize bridge client
bridge = BridgeClient(config.bridge_url) if config.bridge_url else None


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available Revit tools."""

    tools = [
        Tool(
            name="revit_health",
            description="Check if Revit is running and get status information",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
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
                    "level": {"type": "string", "description": "Level name (e.g., 'L1', 'L2')", "default": "L1"}
                },
                "required": ["start_x", "start_y", "end_x", "end_y"]
            }
        ),
        Tool(
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
                                "z": {"type": "number", "default": 0}
                            },
                            "required": ["x", "y"]
                        }
                    },
                    "level": {"type": "string", "description": "Level name", "default": "L1"}
                },
                "required": ["points"]
            }
        ),
        Tool(
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
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "z": {"type": "number"}
                            }
                        }
                    },
                    "level": {"type": "string", "description": "Level name"},
                    "slope": {"type": "number", "description": "Roof slope", "default": 0.5}
                },
                "required": ["points", "level"]
            }
        ),
        Tool(
            name="revit_list_levels",
            description="List all levels in the Revit project",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="revit_list_views",
            description="List all views in the Revit project",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="revit_list_elements",
            description="List elements by category (Walls, Floors, Roofs, Doors, Windows, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category name (e.g., 'Walls', 'Floors', 'Doors')"}
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="revit_get_document_info",
            description="Get information about the active Revit document",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="revit_create_level",
            description="Create a new level in Revit",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Level name"},
                    "elevation": {"type": "number", "description": "Elevation in feet"}
                },
                "required": ["name", "elevation"]
            }
        ),
        Tool(
            name="revit_save_document",
            description="Save the current Revit document",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to save to (optional for existing files)"}
                }
            }
        ),
        Tool(
            name="revit_create_grid",
            description="Create a grid line in Revit",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_x": {"type": "number"}, "start_y": {"type": "number"}, "start_z": {"type": "number", "default": 0},
                    "end_x": {"type": "number"}, "end_y": {"type": "number"}, "end_z": {"type": "number", "default": 0},
                    "name": {"type": "string"}
                },
                "required": ["start_x", "start_y", "end_x", "end_y"]
            }
        ),
        Tool(
            name="revit_create_room",
            description="Create a room at a specific point on a level",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string"},
                    "x": {"type": "number"}, "y": {"type": "number"},
                    "name": {"type": "string", "default": "Room"},
                    "number": {"type": "string"}
                },
                "required": ["level", "x", "y"]
            }
        ),
        Tool(
            name="revit_delete_element",
            description="Delete an element by ID",
            inputSchema={
                "type": "object",
                "properties": {"element_id": {"type": "integer"}},
                "required": ["element_id"]
            }
        ),
        Tool(
            name="revit_place_family_instance",
            description="Place a family instance (e.g., furniture, equipment)",
            inputSchema={
                "type": "object",
                "properties": {
                    "family_name": {"type": "string"}, "type_name": {"type": "string"},
                    "level": {"type": "string"},
                    "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number", "default": 0}
                },
                "required": ["family_name", "type_name", "level", "x", "y"]
            }
        ),
        Tool(
            name="revit_place_door",
            description="Place a door in a wall",
            inputSchema={
                "type": "object",
                "properties": {
                    "wall_id": {"type": "integer"},
                    "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number", "default": 0},
                    "family_name": {"type": "string"}, "type_name": {"type": "string"}
                },
                "required": ["wall_id", "x", "y"]
            }
        ),
        Tool(
            name="revit_place_window",
            description="Place a window in a wall",
            inputSchema={
                "type": "object",
                "properties": {
                    "wall_id": {"type": "integer"},
                    "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number", "default": 0},
                    "family_name": {"type": "string"}, "type_name": {"type": "string"}
                },
                "required": ["wall_id", "x", "y"]
            }
        ),
        Tool(
            name="revit_list_families",
            description="List all loaded families and their types",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="revit_create_floor_plan_view",
            description="Create a floor plan view for a level",
            inputSchema={
                "type": "object", 
                "properties": {"level_name": {"type": "string"}, "view_name": {"type": "string"}},
                "required": ["level_name"]
            }
        ),
        Tool(
            name="revit_create_3d_view",
            description="Create a new 3D view",
            inputSchema={
                "type": "object", 
                "properties": {"view_name": {"type": "string"}},
                "required": ["view_name"]
            }
        ),
        Tool(
            name="revit_create_section_view",
            description="Create a section view",
            inputSchema={
                "type": "object", 
                "properties": {
                    "view_name": {"type": "string"},
                    "start_x": {"type": "number"}, "start_y": {"type": "number"}, "start_z": {"type": "number"},
                    "end_x": {"type": "number"}, "end_y": {"type": "number"}, "end_z": {"type": "number"},
                    "height": {"type": "number", "default": 10}
                },
                "required": ["start_x", "start_y", "end_x", "end_y"]
            }
        ),
        Tool(
            name="revit_get_element_parameters",
            description="Get all parameters of an element",
            inputSchema={
                "type": "object", "properties": {"element_id": {"type": "integer"}}, "required": ["element_id"]
            }
        ),
        Tool(
            name="revit_set_parameter_value",
            description="Set a parameter value for an element",
            inputSchema={
                "type": "object", 
                "properties": {
                    "element_id": {"type": "integer"}, 
                    "parameter_name": {"type": "string"}, 
                    "value": {"type": ["string", "number", "boolean"]}
                }, 
                "required": ["element_id", "parameter_name", "value"]
            }
        ),
        Tool(
            name="revit_get_parameter_value",
            description="Get a specific parameter value",
            inputSchema={
                "type": "object", 
                "properties": {"element_id": {"type": "integer"}, "parameter_name": {"type": "string"}}, 
                "required": ["element_id", "parameter_name"]
            }
        ),
        Tool(
            name="revit_list_shared_parameters",
            description="List shared parameters in the document",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="revit_create_shared_parameter",
            description="Create a new shared parameter",
            inputSchema={
                "type": "object", 
                "properties": {
                    "name": {"type": "string"}, "group": {"type": "string"}, 
                    "type": {"type": "string"}, "visible": {"type": "boolean"}
                }, 
                "required": ["name"]
            }
        ),
        Tool(
            name="revit_list_project_parameters",
            description="List project parameters",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="revit_create_project_parameter",
            description="Create a new project parameter",
            inputSchema={
                "type": "object", 
                "properties": {
                    "name": {"type": "string"}, "category": {"type": "string"}, 
                    "group": {"type": "string"}, "type": {"type": "string"}
                }, 
                "required": ["name", "category"]
            }
        ),
        Tool(
            name="revit_batch_set_parameters",
            description="Set a parameter value for multiple elements",
            inputSchema={
                "type": "object", 
                "properties": {
                    "element_ids": {"type": "array", "items": {"type": "integer"}}, 
                    "parameter_name": {"type": "string"}, "value": {"type": ["string", "number"]}
                }, 
                "required": ["element_ids", "parameter_name", "value"]
            }
        ),
        Tool(
            name="revit_get_type_parameters",
            description="Get type parameters for an element",
            inputSchema={"type": "object", "properties": {"element_id": {"type": "integer"}}, "required": ["element_id"]}
        ),
        Tool(
            name="revit_set_type_parameter",
            description="Set a type parameter value",
            inputSchema={
                "type": "object", 
                "properties": {
                    "element_id": {"type": "integer"}, 
                    "parameter_name": {"type": "string"}, "value": {"type": ["string", "number"]}
                }, 
                "required": ["element_id", "parameter_name", "value"]
            }
        ),
        Tool(
            name="revit_list_sheets",
            description="List all sheets",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="revit_create_sheet",
            description="Create a new sheet",
            inputSchema={
                "type": "object", 
                "properties": {"name": {"type": "string"}, "number": {"type": "string"}, "titleblock_id": {"type": "integer"}}, 
                "required": ["name", "number"]
            }
        ),
        Tool(
            name="revit_delete_sheet",
            description="Delete a sheet",
            inputSchema={"type": "object", "properties": {"sheet_id": {"type": "integer"}}, "required": ["sheet_id"]}
        ),
        Tool(
            name="revit_place_viewport_on_sheet",
            description="Place a view on a sheet",
            inputSchema={
                "type": "object",
                "properties": {
                    "sheet_id": {"type": "integer"}, "view_id": {"type": "integer"},
                    "x": {"type": "number"}, "y": {"type": "number"}
                },
                "required": ["sheet_id", "view_id", "x", "y"]
            }
        ),
        Tool(
            name="revit_batch_create_sheets_from_csv",
            description="Create multiple sheets from a CSV file",
            inputSchema={
                "type": "object", "properties": {"csv_path": {"type": "string"}, "titleblock_name": {"type": "string"}}, 
                "required": ["csv_path"]
            }
        ),
        Tool(
            name="revit_populate_titleblock",
            description="Populate titleblock parameters",
            inputSchema={
                "type": "object", "properties": {"sheet_id": {"type": "integer"}, "parameters": {"type": "object"}}, 
                "required": ["sheet_id", "parameters"]
            }
        ),
        Tool(
            name="revit_list_titleblocks",
            description="List available titleblocks",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="revit_get_sheet_info",
            description="Get detailed information about a sheet",
            inputSchema={"type": "object", "properties": {"sheet_id": {"type": "integer"}}, "required": ["sheet_id"]}
        ),
        Tool(
            name="revit_duplicate_sheet",
            description="Duplicate a sheet",
            inputSchema={
                "type": "object", 
                "properties": {"sheet_id": {"type": "integer"}, "with_views": {"type": "boolean"}, "duplicate_option": {"type": "string"}}, 
                "required": ["sheet_id"]
            }
        ),
        Tool(
            name="revit_renumber_sheets",
            description="Batch renumber sheets",
            inputSchema={
                "type": "object", "properties": {"prefix": {"type": "string"}, "start_number": {"type": "integer"}}, 
                "required": ["start_number"]
            }
        ),

        # Batch 2: Selection
        Tool(name="revit_get_selection", description="Get currently selected element IDs", inputSchema={"type": "object", "properties": {}}),
        Tool(name="revit_set_selection", description="Set selection by element IDs", inputSchema={"type": "object", "properties": {"element_ids": {"type": "array", "items": {"type": "integer"}}}, "required": ["element_ids"]}),

        # Batch 2: Annotation
        Tool(name="revit_create_text_note", description="Create a text note", inputSchema={"type": "object", "properties": {"text": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "view_id": {"type": "integer"}}, "required": ["text", "x", "y"]}),
        Tool(name="revit_create_tag", description="Tag an element", inputSchema={"type": "object", "properties": {"element_id": {"type": "integer"}, "x": {"type": "number"}, "y": {"type": "number"}, "view_id": {"type": "integer"}}, "required": ["element_id", "x", "y"]}),

        # Batch 2: Structure
        Tool(name="revit_create_column", description="Create structural column", inputSchema={"type": "object", "properties": {"family_name": {"type": "string"}, "type_name": {"type": "string"}, "level": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}}, "required": ["family_name", "type_name", "level", "x", "y"]}),
        Tool(name="revit_create_beam", description="Create structural beam", inputSchema={"type": "object", "properties": {"family_name": {"type": "string"}, "type_name": {"type": "string"}, "level": {"type": "string"}, "start_x": {"type": "number"}, "start_y": {"type": "number"}, "end_x": {"type": "number"}, "end_y": {"type": "number"}}, "required": ["family_name", "type_name", "level", "start_x", "start_y", "end_x", "end_y"]}),
        Tool(name="revit_create_foundation", description="Create foundation", inputSchema={"type": "object", "properties": {"family_name": {"type": "string"}, "type_name": {"type": "string"}, "level": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number", "default": 0}}, "required": ["family_name", "type_name", "level", "x", "y"]}),

        # Batch 2: MEP
        Tool(name="revit_create_duct", description="Create duct", inputSchema={"type": "object", "properties": {"level": {"type": "string"}, "start_x": {"type": "number"}, "start_y": {"type": "number"}, "end_x": {"type": "number"}, "end_y": {"type": "number"}, "z": {"type": "number", "default": 10}, "system_type": {"type": "string"}, "duct_type": {"type": "string"}}, "required": ["level", "start_x", "start_y", "end_x", "end_y"]}),
        Tool(name="revit_create_pipe", description="Create pipe", inputSchema={"type": "object", "properties": {"level": {"type": "string"}, "start_x": {"type": "number"}, "start_y": {"type": "number"}, "end_x": {"type": "number"}, "end_y": {"type": "number"}, "z": {"type": "number", "default": 0}, "system_type": {"type": "string"}, "pipe_type": {"type": "string"}}, "required": ["level", "start_x", "start_y", "end_x", "end_y"]}),

        # Batch 2: Helpers
        Tool(name="revit_get_categories", description="List Revit categories", inputSchema={"type": "object", "properties": {}}),
        Tool(name="revit_get_element_type", description="Find element types/families", inputSchema={"type": "object", "properties": {"category_name": {"type": "string"}, "family_name": {"type": "string"}}, "required": ["category_name"]}),

        # Batch 2: Remaining Existing
        Tool(name="revit_close_document", description="Close active document", inputSchema={"type": "object", "properties": {"save_changes": {"type": "boolean", "default": False}}}),
        Tool(name="revit_create_new_document", description="Create new project", inputSchema={"type": "object", "properties": {"template_path": {"type": "string"}}}),
        Tool(name="revit_export_dwg", description="Export view to DWG", inputSchema={"type": "object", "properties": {"view_id": {"type": "integer"}, "output_path": {"type": "string"}}, "required": ["view_id", "output_path"]}),
        Tool(name="revit_export_ifc", description="Export to IFC", inputSchema={"type": "object", "properties": {"output_path": {"type": "string"}}, "required": ["output_path"]}),
        Tool(name="revit_export_navisworks", description="Export to NWC", inputSchema={"type": "object", "properties": {"output_path": {"type": "string"}}, "required": ["output_path"]}),
        Tool(name="revit_export_image", description="Export view to Image", inputSchema={"type": "object", "properties": {"view_id": {"type": "integer"}, "output_path": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}}, "required": ["view_id", "output_path"]}),
        Tool(name="revit_render_3d", description="Render 3D view to image", inputSchema={"type": "object", "properties": {"view_id": {"type": "integer"}, "output_path": {"type": "string"}, "quality": {"type": "string", "enum": ["Draft", "Medium", "High"]}}, "required": ["view_id", "output_path"]}),

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Execute a Revit tool."""

    if not bridge:
        return [TextContent(
            type="text",
            text="Error: Bridge not configured. Set MCP_REVIT_BRIDGE_URL in your .env file."
        )]

    try:
        # Map MCP tool names to Revit bridge tools
        # Geometry (New)
        "revit_create_grid": ("revit.create_grid", {
            "start_point": {"x": arguments.get("start_x"), "y": arguments.get("start_y"), "z": arguments.get("start_z")},
            "end_point": {"x": arguments.get("end_x"), "y": arguments.get("end_y"), "z": arguments.get("end_z")},
            "name": arguments.get("name")
        }),
        "revit_create_room": ("revit.create_room", {
            "level": arguments.get("level"),
            "location_point": {"x": arguments.get("x"), "y": arguments.get("y"), "z": 0},
            "name": arguments.get("name"),
            "number": arguments.get("number")
        }),
        "revit_delete_element": ("revit.delete_element", {
            "element_id": arguments.get("element_id")
        }),

        # Placement (New)
        "revit_place_family_instance": ("revit.place_family_instance", {
            "family_name": arguments.get("family_name"),
            "type_name": arguments.get("type_name"),
            "level": arguments.get("level"),
            "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": arguments.get("z")}
        }),
        "revit_place_door": ("revit.place_door", {
            "wall_id": arguments.get("wall_id"),
            "family_name": arguments.get("family_name"),
            "type_name": arguments.get("type_name"),
            "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": arguments.get("z")}
        }),
        "revit_place_window": ("revit.place_window", {
            "wall_id": arguments.get("wall_id"),
            "family_name": arguments.get("family_name"),
            "type_name": arguments.get("type_name"),
            "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": arguments.get("z")}
        }),
        "revit_list_families": ("revit.list_families", {}),

        # Views (New)
        "revit_create_floor_plan_view": ("revit.create_floor_plan_view", {
            "level_name": arguments.get("level_name"),
            "view_name": arguments.get("view_name")
        }),
        "revit_create_3d_view": ("revit.create_3d_view", {
            "view_name": arguments.get("view_name")
        }),
        "revit_create_section_view": ("revit.create_section_view", {
            "view_name": arguments.get("view_name"),
            "start_point": {"x": arguments.get("start_x"), "y": arguments.get("start_y"), "z": arguments.get("start_z")},
            "end_point": {"x": arguments.get("end_x"), "y": arguments.get("end_y"), "z": arguments.get("end_z")},
            "height": arguments.get("height")
        }),

        # Parameters (New)
        "revit_get_element_parameters": ("revit.get_element_parameters", {
            "element_id": arguments.get("element_id")
        }),
        "revit_set_parameter_value": ("revit.set_parameter_value", {
            "element_id": arguments.get("element_id"),
            "parameter_name": arguments.get("parameter_name"),
            "value": arguments.get("value")
        }),
        "revit_get_parameter_value": ("revit.get_parameter_value", {
            "element_id": arguments.get("element_id"),
            "parameter_name": arguments.get("parameter_name")
        }),
        "revit_list_shared_parameters": ("revit.list_shared_parameters", {}),
        "revit_create_shared_parameter": ("revit.create_shared_parameter", {
             "name": arguments.get("name"),
             "group": arguments.get("group", "General"),
             "type": arguments.get("type", "Text"),
             "visible": arguments.get("visible", True)
        }),
        "revit_list_project_parameters": ("revit.list_project_parameters", {}),
        "revit_create_project_parameter": ("revit.create_project_parameter", {
             "name": arguments.get("name"),
             "group": arguments.get("group", "General"),
             "type": arguments.get("type", "Text"),
             "category": arguments.get("category"),
             "visible": arguments.get("visible", True)
        }),
        "revit_batch_set_parameters": ("revit.batch_set_parameters", {
             "element_ids": arguments.get("element_ids"),
             "parameter_name": arguments.get("parameter_name"),
             "value": arguments.get("value")
        }),
        "revit_get_type_parameters": ("revit.get_type_parameters", {
             "element_id": arguments.get("element_id")
        }),
        "revit_set_type_parameter": ("revit.set_type_parameter", {
             "element_id": arguments.get("element_id"),
             "parameter_name": arguments.get("parameter_name"),
             "value": arguments.get("value")
        }),

        # Sheets (New)
        "revit_list_sheets": ("revit.list_sheets", {}),
        "revit_create_sheet": ("revit.create_sheet", {
             "name": arguments.get("name"),
             "number": arguments.get("number"),
             "titleblock_id": arguments.get("titleblock_id")
        }),
        "revit_delete_sheet": ("revit.delete_sheet", {
             "sheet_id": arguments.get("sheet_id")
        }),
        "revit_place_viewport_on_sheet": ("revit.place_viewport_on_sheet", {
             "sheet_id": arguments.get("sheet_id"),
             "view_id": arguments.get("view_id"),
             "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": 0}
        }),
        "revit_batch_create_sheets_from_csv": ("revit.batch_create_sheets_from_csv", {
             "csv_path": arguments.get("csv_path"),
             "titleblock_name": arguments.get("titleblock_name")
        }),
        "revit_populate_titleblock": ("revit.populate_titleblock", {
             "sheet_id": arguments.get("sheet_id"),
             "parameters": arguments.get("parameters")
        }),
        "revit_list_titleblocks": ("revit.list_titleblocks", {}),
        "revit_get_sheet_info": ("revit.get_sheet_info", {
             "sheet_id": arguments.get("sheet_id")
        }),
        "revit_duplicate_sheet": ("revit.duplicate_sheet", {
             "sheet_id": arguments.get("sheet_id"),
             "with_views": arguments.get("with_views", False),
             "duplicate_option": arguments.get("duplicate_option", "Duplicate")
        }),
        "revit_renumber_sheets": ("revit.renumber_sheets", {
             "prefix": arguments.get("prefix"),
             "start_number": arguments.get("start_number")
        }),
        
        # Existing
        "revit_health": ("revit.health", {}),
        "revit_list_levels": ("revit.list_levels", {}),
        "revit_list_views": ("revit.list_views", {}),
        "revit_get_document_info": ("revit.get_document_info", {}),
        "revit_list_elements": ("revit.list_elements_by_category", {
            "category": arguments.get("category", "Walls")
        }),
        "revit_create_wall": ("revit.create_wall", {
            "start_point": {
                "x": arguments.get("start_x", 0),
                "y": arguments.get("start_y", 0),
                "z": arguments.get("start_z", 0)
            },
            "end_point": {
                "x": arguments.get("end_x", 0),
                "y": arguments.get("end_y", 0),
                "z": arguments.get("end_z", 0)
            },
            "height": arguments.get("height", 10),
            "level": arguments.get("level", "L1")
        }),
        "revit_create_floor": ("revit.create_floor", {
            "boundary_points": [
                {"x": p.get("x", 0), "y": p.get("y", 0), "z": p.get("z", 0)}
                for p in arguments.get("points", [])
            ],
            "level": arguments.get("level", "L1")
        }),
        "revit_create_roof": ("revit.create_roof", {
            "boundary_points": [
                {"x": p.get("x", 0), "y": p.get("y", 0), "z": p.get("z", 0)}
                for p in arguments.get("points", [])
            ],
            "level": arguments.get("level", "Level 2"),
            "slope": arguments.get("slope", 0.5)
        }),
        "revit_create_level": ("revit.create_level", {
            "name": arguments.get("name", "New Level"),
            "elevation": arguments.get("elevation", 10)
        }),
        "revit_save_document": ("revit.save_document", {
            "path": arguments.get("path", "")
        }),

        # Batch 2: Selection
        "revit_get_selection": ("revit.get_selection", {}),
        "revit_set_selection": ("revit.set_selection", {"element_ids": arguments.get("element_ids")}),

        # Batch 2: Annotation
        "revit_create_text_note": ("revit.create_text_note", {"text": arguments.get("text"), "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": 0}, "view_id": arguments.get("view_id")}),
        "revit_create_tag": ("revit.create_tag", {"element_id": arguments.get("element_id"), "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": 0}, "view_id": arguments.get("view_id")}),

        # Batch 2: Structure
        "revit_create_column": ("revit.create_column", {"family_name": arguments.get("family_name"), "type_name": arguments.get("type_name"), "level": arguments.get("level"), "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": 0}}),
        "revit_create_beam": ("revit.create_beam", {"family_name": arguments.get("family_name"), "type_name": arguments.get("type_name"), "level": arguments.get("level"), "start_point": {"x": arguments.get("start_x"), "y": arguments.get("start_y"), "z": 0}, "end_point": {"x": arguments.get("end_x"), "y": arguments.get("end_y"), "z": 0}}),
        "revit_create_foundation": ("revit.create_foundation", {"family_name": arguments.get("family_name"), "type_name": arguments.get("type_name"), "level": arguments.get("level"), "location": {"x": arguments.get("x"), "y": arguments.get("y"), "z": arguments.get("z", 0)}}),

        # Batch 2: MEP
        "revit_create_duct": ("revit.create_duct", {"level": arguments.get("level"), "start_point": {"x": arguments.get("start_x"), "y": arguments.get("start_y"), "z": arguments.get("z", 10)}, "end_point": {"x": arguments.get("end_x"), "y": arguments.get("end_y"), "z": arguments.get("z", 10)}, "system_type": arguments.get("system_type"), "duct_type": arguments.get("duct_type")}),
        "revit_create_pipe": ("revit.create_pipe", {"level": arguments.get("level"), "start_point": {"x": arguments.get("start_x"), "y": arguments.get("start_y"), "z": arguments.get("z", 0)}, "end_point": {"x": arguments.get("end_x"), "y": arguments.get("end_y"), "z": arguments.get("z", 0)}, "system_type": arguments.get("system_type"), "pipe_type": arguments.get("pipe_type")}),

        # Batch 2: Helpers
        "revit_get_categories": ("revit.get_categories", {}),
        "revit_get_element_type": ("revit.get_element_type", {"category_name": arguments.get("category_name"), "family_name": arguments.get("family_name")}),

        # Batch 2: Remaining Existing
        "revit_close_document": ("revit.close_document", {"save_changes": arguments.get("save_changes", False)}),
        "revit_create_new_document": ("revit.create_new_document", {"template_path": arguments.get("template_path")}),
        "revit_export_dwg": ("revit.export_dwg_by_view", {"view_id": arguments.get("view_id"), "output_path": arguments.get("output_path")}),
        "revit_export_ifc": ("revit.export_ifc_with_settings", {"output_path": arguments.get("output_path")}),
        "revit_export_navisworks": ("revit.export_navisworks", {"output_path": arguments.get("output_path")}),
        "revit_export_image": ("revit.export_image", {"view_id": arguments.get("view_id"), "output_path": arguments.get("output_path"), "width": arguments.get("width"), "height": arguments.get("height")}),
        "revit_render_3d": ("revit.render_3d_view", {"view_id": arguments.get("view_id"), "output_path": arguments.get("output_path"), "quality": arguments.get("quality", "Medium")}),

        # Batch 3: Editing
        "revit_move_element": ("revit.move_element", {"element_id": arguments.get("element_id"), "vector": {"x": arguments.get("x"), "y": arguments.get("y"), "z": arguments.get("z", 0)}}),
        "revit_copy_element": ("revit.copy_element", {"element_id": arguments.get("element_id"), "vector": {"x": arguments.get("x"), "y": arguments.get("y"), "z": arguments.get("z", 0)}}),
        "revit_rotate_element": ("revit.rotate_element", {"element_id": arguments.get("element_id"), "axis_point": {"x": arguments.get("center_x"), "y": arguments.get("center_y"), "z": arguments.get("center_z", 0)}, "angle_radians": arguments.get("angle_radians")}),
        "revit_mirror_element": ("revit.mirror_element", {"element_id": arguments.get("element_id"), "plane_origin": {"x": arguments.get("plane_origin_x"), "y": arguments.get("plane_origin_y"), "z": arguments.get("plane_origin_z", 0)}, "plane_normal": {"x": arguments.get("plane_normal_x"), "y": arguments.get("plane_normal_y"), "z": arguments.get("plane_normal_z", 0)}}),
        "revit_pin_element": ("revit.pin_element", {"element_id": arguments.get("element_id")}),
        "revit_unpin_element": ("revit.unpin_element", {"element_id": arguments.get("element_id")}),

        # Batch 3: Worksharing
        "revit_sync_to_central": ("revit.sync_to_central", {"comment": arguments.get("comment", "Sync via MCP"), "relinquish": arguments.get("relinquish", True)}),
        "revit_relinquish_all": ("revit.relinquish_all", {}),
        "revit_get_worksets": ("revit.get_worksets", {}),

        # Batch 3: Schedules & Geo
        "revit_create_schedule": ("revit.create_schedule", {"category_name": arguments.get("category_name"), "name": arguments.get("name")}),
        "revit_get_schedule_data": ("revit.get_schedule_data", {"schedule_id": arguments.get("schedule_id")}),
        "revit_get_element_bounding_box": ("revit.get_element_bounding_box", {"element_id": arguments.get("element_id")}),
    }

        if name not in tool_mapping:
            return [TextContent(
                type="text",
                text=f"Error: Unknown tool '{name}'"
            )]

        bridge_tool, payload = tool_mapping[name]

        # Call the bridge
        result = bridge.call_tool(bridge_tool, payload)

        # Format the response
        response_text = f"✓ {name} executed successfully\n\n"
        response_text += f"Result:\n{json.dumps(result, indent=2)}"

        return [TextContent(type="text", text=response_text)]

    except BridgeError as e:
        error_msg = f"Revit Bridge Error: {str(e)}\n\n"
        error_msg += "Make sure:\n"
        error_msg += "1. Revit is running\n"
        error_msg += "2. A project is open in Revit\n"
        error_msg += "3. The RevitMCP Bridge add-in is loaded\n"
        error_msg += "4. The bridge is accessible at http://localhost:3000"

        return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def run_mcp_server():
    """Entry point for running the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    run_mcp_server()
