"""
Test script for RevitMCP with Universal Bridge (10,000+ tools)
Tests the latest features including reflection-based API access
"""
import requests
import json
import time

BRIDGE_URL = "http://127.0.0.1:3000"

def test_tool(tool_name, payload, description):
    """Test a Revit tool through the bridge."""
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"Tool: {tool_name}")
    print(f"{'='*70}")

    request_data = {
        "tool": tool_name,
        "payload": payload,
        "request_id": f"test-{int(time.time())}"
    }

    try:
        response = requests.post(
            f"{BRIDGE_URL}/execute",
            json=request_data,
            timeout=30
        )

        result = response.json()
        status = result.get('Status', result.get('status', 'unknown'))

        if status.lower() == 'ok':
            print(f"✓ SUCCESS")
            res_data = result.get('Result', result.get('result', {}))
            print(f"\nResult:")
            print(json.dumps(res_data, indent=2))
            return res_data
        else:
            print(f"✗ FAILED")
            print(f"Error: {result.get('Message', result.get('message', 'Unknown'))}")
            return None

    except Exception as e:
        print(f"✗ ERROR: {e}")
        return None

def main():
    """Run comprehensive tests of RevitMCP features."""

    print("="*70)
    print("RevitMCP - Latest Features Test Suite")
    print("Universal Bridge with 10,000+ tools")
    print("="*70)

    # Test 1: Health Check
    print("\n" + "="*70)
    print("PHASE 1: CONNECTIVITY & STATUS")
    print("="*70)

    test_tool("revit.health", {}, "Check Revit bridge status")

    doc_info = test_tool("revit.get_document_info", {}, "Get active document information")

    # Test 2: List Available Resources
    print("\n" + "="*70)
    print("PHASE 2: AVAILABLE RESOURCES")
    print("="*70)

    levels = test_tool("revit.list_levels", {}, "List all levels in project")

    if levels and levels.get('levels'):
        level_name = levels['levels'][0]['name']
        print(f"\n✓ Found level: {level_name}")
    else:
        level_name = "L1"
        print(f"\n⚠ No levels found, using default: {level_name}")

    test_tool("revit.list_views", {}, "List all views in project")

    # Test 3: Create Geometry (Basic Tools)
    print("\n" + "="*70)
    print("PHASE 3: BASIC GEOMETRY CREATION")
    print("="*70)

    # Create a simple wall
    wall = test_tool(
        "revit.create_wall",
        {
            "start_point": {"x": 0, "y": 0, "z": 0},
            "end_point": {"x": 20, "y": 0, "z": 0},
            "height": 10,
            "level": level_name
        },
        "Create a 20ft wall"
    )

    # Create a floor
    floor = test_tool(
        "revit.create_floor",
        {
            "boundary_points": [
                {"x": 0, "y": 0, "z": 0},
                {"x": 20, "y": 0, "z": 0},
                {"x": 20, "y": 15, "z": 0},
                {"x": 0, "y": 15, "z": 0}
            ],
            "level": level_name
        },
        "Create a 20x15 floor slab"
    )

    # Test 4: Query Created Elements
    print("\n" + "="*70)
    print("PHASE 4: QUERY ELEMENTS")
    print("="*70)

    walls = test_tool(
        "revit.list_elements_by_category",
        {"category": "Walls"},
        "List all walls in project"
    )

    if walls:
        print(f"\n✓ Total walls in model: {walls.get('count', 0)}")

    floors = test_tool(
        "revit.list_elements_by_category",
        {"category": "Floors"},
        "List all floors in project"
    )

    if floors:
        print(f"\n✓ Total floors in model: {floors.get('count', 0)}")

    # Test 5: Universal Bridge Features
    print("\n" + "="*70)
    print("PHASE 5: UNIVERSAL BRIDGE (REFLECTION)")
    print("="*70)
    print("Testing dynamic API access via reflection...")

    # Note: The actual reflection API endpoints would be tested here
    # This depends on the specific implementation in the latest version

    # Test listing available namespaces/types (if implemented)
    reflection_test = test_tool(
        "revit.reflection.list_types",
        {"namespace": "Autodesk.Revit.DB"},
        "List available Revit API types (if implemented)"
    )

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    print("\n✓ Tested Features:")
    print("  • Health check and status")
    print("  • Document information")
    print("  • Level and view enumeration")
    print("  • Wall creation")
    print("  • Floor creation")
    print("  • Element queries")
    print("  • Universal Bridge (reflection)")

    print("\n" + "="*70)
    print("Testing complete!")
    print("="*70)

    print("\nNext steps:")
    print("1. Try creating more complex geometry")
    print("2. Test exports (PDF, DWG, IFC)")
    print("3. Use Claude Desktop for natural language control")
    print("4. Explore the 10,000+ available tools")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
