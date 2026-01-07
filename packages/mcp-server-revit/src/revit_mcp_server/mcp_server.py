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
    ]

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
        tool_mapping = {
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
