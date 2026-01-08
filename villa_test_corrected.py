import requests
import json

URL = "http://localhost:3000/execute"

def test(tool, payload={}):
    req_id = f"test-{test.counter}"
    test.counter += 1

    print(f"\n[Test {test.counter}] {tool}")
    print("-" * 60)

    data = {"request_id": req_id, "tool": tool, "payload": payload}

    try:
        r = requests.post(URL, json=data, timeout=30)
        result = r.json()

        if result.get("Status") == "ok":
            print(f"PASS - {tool}")
            result_data = result.get("Result")
            print(json.dumps(result_data, indent=2)[:500])
            return result_data
        else:
            print(f"FAIL - {tool}")
            print(f"Error: {result.get('Message')}")
            print(f"Full Response: {json.dumps(result, indent=2)[:500]}")
            return None
    except Exception as e:
        print(f"EXCEPTION - {str(e)}")
        return None

test.counter = 0

print("\n" + "="*60)
print("REVIT MCP - VILLA BUILDING TEST (CORRECTED)")
print("="*60)

# Test 1: Health
test("revit.health")

# Test 2: Document Info
test("revit.get_document_info")

# Test 3: List Levels
levels = test("revit.list_levels")

# Test 4: Create First Floor Level (already created, will skip)
# test("revit.create_level", {"name": "First Floor", "elevation": 3500})

# Test 5: Create Roof Level (already created, will skip)
# test("revit.create_level", {"name": "Roof", "elevation": 7000})

# Test 6: List Levels Again
test("revit.list_levels")

# Test 7-10: Create External Walls - FIXED PARAMETERS
print("\n" + "="*60)
print("Creating External Walls (10m x 12m) - CORRECTED")
print("="*60)

# South wall - CORRECTED: start_point, end_point, level (not level_name)
test("revit.create_wall", {
    "start_point": [0, 0, 0],
    "end_point": [10000, 0, 0],
    "height": 2800,
    "level": "L1"
})

# East wall
test("revit.create_wall", {
    "start_point": [10000, 0, 0],
    "end_point": [10000, 12000, 0],
    "height": 2800,
    "level": "L1"
})

# North wall
test("revit.create_wall", {
    "start_point": [10000, 12000, 0],
    "end_point": [0, 12000, 0],
    "height": 2800,
    "level": "L1"
})

# West wall
test("revit.create_wall", {
    "start_point": [0, 12000, 0],
    "end_point": [0, 0, 0],
    "height": 2800,
    "level": "L1"
})

# Test 11-13: Internal Walls - CORRECTED
print("\n" + "="*60)
print("Creating Internal Walls - CORRECTED")
print("="*60)

# Hallway wall
test("revit.create_wall", {
    "start_point": [3000, 0, 0],
    "end_point": [3000, 12000, 0],
    "height": 2800,
    "level": "L1"
})

# Bedroom divider
test("revit.create_wall", {
    "start_point": [3000, 6000, 0],
    "end_point": [10000, 6000, 0],
    "height": 2800,
    "level": "L1"
})

# Bathroom wall
test("revit.create_wall", {
    "start_point": [7000, 0, 0],
    "end_point": [7000, 6000, 0],
    "height": 2800,
    "level": "L1"
})

# Test 14: List Walls
print("\n" + "="*60)
print("Query Created Walls")
print("="*60)
test("revit.list_elements_by_category", {"category": "Walls"})

# Test 15: Create Floor - CORRECTED
print("\n" + "="*60)
print("Creating Floor Slab - CORRECTED")
print("="*60)
# CORRECTED: boundary_points (not boundary), level (not level_name)
test("revit.create_floor", {
    "boundary_points": [
        [0, 0, 0],
        [10000, 0, 0],
        [10000, 12000, 0],
        [0, 12000, 0]
    ],
    "level": "L1"
})

# Test 16: Create Rooms - CORRECTED
print("\n" + "="*60)
print("Creating Rooms - CORRECTED")
print("="*60)

# CORRECTED: location_point (not location), level (not level_name)
test("revit.create_room", {
    "location_point": [1500, 6000, 0],
    "level": "L1",
    "name": "Living Room",
    "number": "101"
})

test("revit.create_room", {
    "location_point": [6500, 3000, 0],
    "level": "L1",
    "name": "Bedroom 1",
    "number": "102"
})

test("revit.create_room", {
    "location_point": [6500, 9000, 0],
    "level": "L1",
    "name": "Bedroom 2",
    "number": "103"
})

test("revit.create_room", {
    "location_point": [8500, 3000, 0],
    "level": "L1",
    "name": "Bathroom",
    "number": "104"
})

# Test 17: Save - Need to use SaveAs first
print("\n" + "="*60)
print("Document Status")
print("="*60)
test("revit.get_document_info")

print("\n" + "="*60)
print(f"COMPLETE - {test.counter} tests run")
print("="*60)
print("\nNOTE: Document not saved - use File > Save As in Revit to save as TestVilla.rvt")
