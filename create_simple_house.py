"""
Create a simple house in Revit - simplified version with correct parameters
"""
import requests
import json

BRIDGE_URL = "http://127.0.0.1:3000"

def call_tool(tool, payload):
    """Call a Revit tool."""
    data = {"tool": tool, "payload": payload, "request_id": f"{tool}-{hash(str(payload))}"}
    response = requests.post(f"{BRIDGE_URL}/execute", json=data, timeout=30)
    result = response.json()

    status = result.get('Status', 'unknown')
    print(f"\n[{tool}] Status: {status}")

    if status.lower() == 'error':
        print(f"  Error: {result.get('Message', 'Unknown')}")
        return None
    else:
        res = result.get('Result', {})
        if res:
            print(f"  Result: {json.dumps(res, indent=4)}")
        return res

print("=" * 70)
print("CREATING A SIMPLE HOUSE IN REVIT")
print("=" * 70)

# Check available levels
print("\n1. Checking available levels...")
levels = call_tool("revit.list_levels", {})
if levels:
    print(f"   Found {levels['count']} levels")
    for l in levels['levels']:
        print(f"     - {l['name']} @ {l['elevation_ft']:.2f} ft")

# Create 4 walls (30ft x 25ft house)
print("\n2. Creating exterior walls...")

walls = []
wall_coords = [
    ("South", (0, 0, 0), (30, 0, 0)),
    ("East", (30, 0, 0), (30, 25, 0)),
    ("North", (30, 25, 0), (0, 25, 0)),
    ("West", (0, 25, 0), (0, 0, 0))
]

for name, start, end in wall_coords:
    print(f"\n   Creating {name} wall...")
    wall = call_tool("revit.create_wall", {
        "start_point": {"x": start[0], "y": start[1], "z": start[2]},
        "end_point": {"x": end[0], "y": end[1], "z": end[2]},
        "height": 10,
        "level": "L1"
    })
    if wall:
        walls.append(wall)

print(f"\n   [OK] Created {len(walls)} walls")

# Create floor
print("\n3. Creating floor slab...")
floor = call_tool("revit.create_floor", {
    "boundary_points": [
        {"x": 0, "y": 0, "z": 0},
        {"x": 30, "y": 0, "z": 0},
        {"x": 30, "y": 25, "z": 0},
        {"x": 0, "y": 25, "z": 0}
    ],
    "level": "L1"
})

if floor:
    print("   [OK] Floor created")

# List what we created
print("\n4. Verifying created elements...")
walls_check = call_tool("revit.list_elements_by_category", {"category": "Walls"})
if walls_check:
    print(f"   Total walls in model: {walls_check['count']}")

floors_check = call_tool("revit.list_elements_by_category", {"category": "Floors"})
if floors_check:
    print(f"   Total floors in model: {floors_check['count']}")

# Get document info
print("\n5. Document info...")
doc_info = call_tool("revit.get_document_info", {})

print("\n" + "=" * 70)
print("HOUSE CREATION COMPLETE!")
print("=" * 70)
print(f"\nCreated in Revit:")
print(f"  - {len(walls)} exterior walls (30ft x 25ft footprint)")
print(f"  - 1 floor slab")
print(f"  - Wall height: 10 feet")
print("\nCheck your Revit window to see the simple house structure!")
print("=" * 70)
