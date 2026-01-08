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
            print(json.dumps(result.get("Result"), indent=2)[:500])
            return result.get("Result")
        else:
            print(f"FAIL - {tool}")
            print(f"Error: {result.get('Message')}")
            return None
    except Exception as e:
        print(f"EXCEPTION - {str(e)}")
        return None

test.counter = 0

print("\n" + "="*60)
print("REVIT MCP - VILLA BUILDING TEST")
print("="*60)

# Test 1: Health
test("revit.health")

# Test 2: Document Info
test("revit.get_document_info")

# Test 3: List Levels
levels = test("revit.list_levels")

# Test 4: Create First Floor Level
test("revit.create_level", {"name": "First Floor", "elevation": 3500})

# Test 5: Create Roof Level
test("revit.create_level", {"name": "Roof", "elevation": 7000})

# Test 6: List Levels Again
test("revit.list_levels")

# Test 7-10: Create External Walls
print("\n" + "="*60)
print("Creating External Walls (10m x 12m)")
print("="*60)

# South wall
test("revit.create_wall", {
    "start": [0, 0, 0],
    "end": [10000, 0, 0],
    "height": 2800,
    "level_name": "Level 1"
})

# East wall
test("revit.create_wall", {
    "start": [10000, 0, 0],
    "end": [10000, 12000, 0],
    "height": 2800,
    "level_name": "Level 1"
})

# North wall
test("revit.create_wall", {
    "start": [10000, 12000, 0],
    "end": [0, 12000, 0],
    "height": 2800,
    "level_name": "Level 1"
})

# West wall
test("revit.create_wall", {
    "start": [0, 12000, 0],
    "end": [0, 0, 0],
    "height": 2800,
    "level_name": "Level 1"
})

# Test 11-13: Internal Walls
print("\n" + "="*60)
print("Creating Internal Walls")
print("="*60)

# Hallway wall
test("revit.create_wall", {
    "start": [3000, 0, 0],
    "end": [3000, 12000, 0],
    "height": 2800,
    "level_name": "Level 1"
})

# Bedroom divider
test("revit.create_wall", {
    "start": [3000, 6000, 0],
    "end": [10000, 6000, 0],
    "height": 2800,
    "level_name": "Level 1"
})

# Bathroom wall
test("revit.create_wall", {
    "start": [7000, 0, 0],
    "end": [7000, 6000, 0],
    "height": 2800,
    "level_name": "Level 1"
})

# Test 14: List Walls
print("\n" + "="*60)
print("Query Created Walls")
print("="*60)
test("revit.list_elements_by_category", {"category": "Walls"})

# Test 15: Create Floor
print("\n" + "="*60)
print("Creating Floor Slab")
print("="*60)
test("revit.create_floor", {
    "boundary": [
        [0, 0, 0],
        [10000, 0, 0],
        [10000, 12000, 0],
        [0, 12000, 0]
    ],
    "level_name": "Level 1"
})

# Test 16: Create Rooms
print("\n" + "="*60)
print("Creating Rooms")
print("="*60)

test("revit.create_room", {
    "location": [1500, 6000, 0],
    "level_name": "Level 1",
    "name": "Living Room",
    "number": "101"
})

test("revit.create_room", {
    "location": [6500, 3000, 0],
    "level_name": "Level 1",
    "name": "Bedroom 1",
    "number": "102"
})

test("revit.create_room", {
    "location": [6500, 9000, 0],
    "level_name": "Level 1",
    "name": "Bedroom 2",
    "number": "103"
})

test("revit.create_room", {
    "location": [8500, 3000, 0],
    "level_name": "Level 1",
    "name": "Bathroom",
    "number": "104"
})

# Test 17: Save
print("\n" + "="*60)
print("Saving Document")
print("="*60)
test("revit.save_document")

print("\n" + "="*60)
print(f"COMPLETE - {test.counter} tests run")
print("="*60)
