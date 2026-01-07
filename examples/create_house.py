"""
Script to create a simple house in Revit using the MCP Bridge.
This demonstrates the RevitMCP server capabilities.
"""
import requests
import json
import time
from typing import Dict, Any

BRIDGE_URL = "http://127.0.0.1:3000"

def call_tool(tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call a Revit tool through the bridge."""
    request_id = f"{tool_name}-{int(time.time())}"

    data = {
        "tool": tool_name,
        "payload": payload,
        "request_id": request_id
    }

    print(f"\n{'='*60}")
    print(f"Calling: {tool_name}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(
            f"{BRIDGE_URL}/execute",
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        # Handle both "status" and "Status" (Revit bridge uses capital S)
        status = result.get('Status', result.get('status', 'unknown'))
        print(f"Status: {status}")

        if status.lower() == 'error' or result.get('status') == 'error':
            message = result.get('Message', result.get('message', 'Unknown error'))
            print(f"Error: {message}")
            if 'StackTrace' in result or 'stack_trace' in result:
                stack = result.get('StackTrace', result.get('stack_trace', ''))
                print(f"Stack trace:\n{stack}")
        else:
            res_data = result.get('Result', result.get('result', {}))
            print(f"Result: {json.dumps(res_data, indent=2)}")

        return result
    except Exception as e:
        print(f"ERROR: {e}")
        return {"status": "error", "message": str(e)}

def check_health():
    """Check if bridge is healthy."""
    print("Checking bridge health...")
    response = requests.get(f"{BRIDGE_URL}/health")
    health = response.json()
    print(f"Bridge Status: {health.get('status')}")
    print(f"Revit Version: {health.get('revit_version')}")
    print(f"Active Document: {health.get('active_document')}")
    return health

def create_simple_house():
    """Create a simple house in Revit."""

    print("\n" + "="*60)
    print("CREATING A SIMPLE HOUSE IN REVIT")
    print("="*60)

    # Check health
    health = check_health()

    # Check if we need to create a new document
    if health.get('active_document') == 'none':
        print("\nNo active document. Creating new Revit project...")
        result = call_tool("revit.create_new_document", {
            "template": "default"
        })
        if result.get('status') == 'error':
            print("Failed to create document. Please open a Revit project manually.")
            return
        time.sleep(2)

    # Get document info
    print("\n--- Getting Document Info ---")
    doc_info = call_tool("revit.get_document_info", {})

    # List existing levels
    print("\n--- Listing Existing Levels ---")
    levels_result = call_tool("revit.list_levels", {})

    # Assume we have a "Level 1" from the template
    # House dimensions: 10m x 8m (approximately 33ft x 26ft)

    # Step 1: Create exterior walls (rectangular floor plan)
    print("\n" + "="*60)
    print("STEP 1: Creating Exterior Walls")
    print("="*60)

    # Wall coordinates in feet (Revit uses imperial units by default)
    # Creating a 30ft x 25ft house
    wall_height = 10  # 10 feet

    # South wall (bottom)
    print("\n--- Creating South Wall ---")
    call_tool("revit.create_wall", {
        "start_point": {"x": 0, "y": 0, "z": 0},
        "end_point": {"x": 30, "y": 0, "z": 0},
        "height": wall_height,
        "level": "Level 1",
        "wall_type": "Generic - 8\""
    })

    # East wall (right)
    print("\n--- Creating East Wall ---")
    call_tool("revit.create_wall", {
        "start_point": {"x": 30, "y": 0, "z": 0},
        "end_point": {"x": 30, "y": 25, "z": 0},
        "height": wall_height,
        "level": "Level 1",
        "wall_type": "Generic - 8\""
    })

    # North wall (top)
    print("\n--- Creating North Wall ---")
    call_tool("revit.create_wall", {
        "start_point": {"x": 30, "y": 25, "z": 0},
        "end_point": {"x": 0, "y": 25, "z": 0},
        "height": wall_height,
        "level": "Level 1",
        "wall_type": "Generic - 8\""
    })

    # West wall (left)
    print("\n--- Creating West Wall ---")
    call_tool("revit.create_wall", {
        "start_point": {"x": 0, "y": 25, "z": 0},
        "end_point": {"x": 0, "y": 0, "z": 0},
        "height": wall_height,
        "level": "Level 1",
        "wall_type": "Generic - 8\""
    })

    # Step 2: Create floor
    print("\n" + "="*60)
    print("STEP 2: Creating Floor Slab")
    print("="*60)

    call_tool("revit.create_floor", {
        "boundary_points": [
            {"x": 0, "y": 0, "z": 0},
            {"x": 30, "y": 0, "z": 0},
            {"x": 30, "y": 25, "z": 0},
            {"x": 0, "y": 25, "z": 0}
        ],
        "level": "Level 1",
        "floor_type": "Generic - 12\""
    })

    # Step 3: Create Level 2 for roof
    print("\n" + "="*60)
    print("STEP 3: Creating Level 2 for Roof")
    print("="*60)

    call_tool("revit.create_level", {
        "elevation": wall_height,
        "name": "Level 2"
    })

    # Step 4: Create roof
    print("\n" + "="*60)
    print("STEP 4: Creating Roof")
    print("="*60)

    call_tool("revit.create_roof", {
        "boundary_points": [
            {"x": -2, "y": -2, "z": wall_height},
            {"x": 32, "y": -2, "z": wall_height},
            {"x": 32, "y": 27, "z": wall_height},
            {"x": -2, "y": 27, "z": wall_height}
        ],
        "level": "Level 2",
        "roof_type": "Generic - 12\"",
        "slope": 0.5  # 6/12 pitch
    })

    # Step 5: Add door (centered on south wall)
    print("\n" + "="*60)
    print("STEP 5: Adding Front Door")
    print("="*60)

    call_tool("revit.place_door", {
        "location": {"x": 15, "y": 0, "z": 0},
        "level": "Level 1",
        "family_name": "Single-Flush",
        "type_name": "36\" x 84\""
    })

    # Step 6: Add windows
    print("\n" + "="*60)
    print("STEP 6: Adding Windows")
    print("="*60)

    # Window on east wall
    call_tool("revit.place_window", {
        "location": {"x": 30, "y": 12.5, "z": 3},
        "level": "Level 1",
        "family_name": "Fixed",
        "type_name": "36\" x 48\""
    })

    # Window on west wall
    call_tool("revit.place_window", {
        "location": {"x": 0, "y": 12.5, "z": 3},
        "level": "Level 1",
        "family_name": "Fixed",
        "type_name": "36\" x 48\""
    })

    # Window on north wall
    call_tool("revit.place_window", {
        "location": {"x": 15, "y": 25, "z": 3},
        "level": "Level 1",
        "family_name": "Fixed",
        "type_name": "36\" x 48\""
    })

    # Step 7: Create a 3D view to see the result
    print("\n" + "="*60)
    print("STEP 7: Creating 3D View")
    print("="*60)

    call_tool("revit.create_3d_view", {
        "view_name": "House 3D View"
    })

    # Save the document
    print("\n" + "="*60)
    print("SAVING DOCUMENT")
    print("="*60)

    call_tool("revit.save_document", {})

    print("\n" + "="*60)
    print("HOUSE CREATION COMPLETE!")
    print("="*60)
    print("\nCheck your Revit window to see the simple house.")
    print("A 30ft x 25ft house with:")
    print("  - 4 exterior walls")
    print("  - Floor slab")
    print("  - Roof")
    print("  - 1 door (front)")
    print("  - 3 windows (sides and back)")

if __name__ == "__main__":
    try:
        create_simple_house()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
