# Villa Building Test - MCP Commands

**Date:** 2026-01-08
**Goal:** Test all available MCP tools by building a complete villa

---

## Test Setup

### Step 1: Create New Project
1. In Revit: File > New > Architectural Template
2. Save as "TestVilla_2026-01-08.rvt"

### Step 2: Test Document Tools
Use Claude Desktop or MCP client to connect and run:

```json
// Test 1: List open documents
{
  "tool": "list_documents"
}

// Test 2: Get active document info
{
  "tool": "get_active_document"
}

// Test 3: Get document details
{
  "tool": "get_document_info"
}
```

**Expected Result:** Should return your TestVilla document information

---

## Phase 1: Create Levels

### Test Level Tools

```json
// Test 4: List existing levels
{
  "tool": "list_levels"
}

// Test 5: Create First Floor level
{
  "tool": "create_level",
  "arguments": {
    "name": "First Floor",
    "elevation": 3500
  }
}

// Test 6: Create Roof level
{
  "tool": "create_level",
  "arguments": {
    "name": "Roof",
    "elevation": 7000
  }
}

// Test 7: List levels again to verify
{
  "tool": "list_levels"
}
```

**Expected Result:**
- Should see Level 1, Level 2 (existing)
- New levels: First Floor (3500mm), Roof (7000mm)

---

## Phase 2: Create External Walls

### Test Wall Creation Tools

```json
// Test 8: List available wall types
{
  "tool": "list_wall_types"
}

// Test 9: Get all elements to understand structure
{
  "tool": "get_all_elements"
}

// Test 10: Create South Wall (10m width)
{
  "tool": "create_wall",
  "arguments": {
    "startPoint": [0, 0, 0],
    "endPoint": [10000, 0, 0],
    "height": 2800,
    "levelName": "Level 1",
    "wallTypeName": "Generic - 200mm"
  }
}

// Test 11: Create East Wall (12m length)
{
  "tool": "create_wall",
  "arguments": {
    "startPoint": [10000, 0, 0],
    "endPoint": [10000, 12000, 0],
    "height": 2800,
    "levelName": "Level 1",
    "wallTypeName": "Generic - 200mm"
  }
}

// Test 12: Create North Wall
{
  "tool": "create_wall",
  "arguments": {
    "startPoint": [10000, 12000, 0],
    "endPoint": [0, 12000, 0],
    "height": 2800,
    "levelName": "Level 1",
    "wallTypeName": "Generic - 200mm"
  }
}

// Test 13: Create West Wall
{
  "tool": "create_wall",
  "arguments": {
    "startPoint": [0, 12000, 0],
    "endPoint": [0, 0, 0],
    "height": 2800,
    "levelName": "Level 1",
    "wallTypeName": "Generic - 200mm"
  }
}
```

**Expected Result:** 4 walls forming 10m x 12m rectangle

---

## Phase 3: Create Internal Walls

### Test Interior Partition Walls

```json
// Test 14: Create hallway wall
{
  "tool": "create_wall",
  "arguments": {
    "startPoint": [3000, 0, 0],
    "endPoint": [3000, 12000, 0],
    "height": 2800,
    "levelName": "Level 1",
    "wallTypeName": "Generic - 100mm"
  }
}

// Test 15: Create bedroom divider
{
  "tool": "create_wall",
  "arguments": {
    "startPoint": [3000, 6000, 0],
    "endPoint": [10000, 6000, 0],
    "height": 2800,
    "levelName": "Level 1",
    "wallTypeName": "Generic - 100mm"
  }
}

// Test 16: Create bathroom wall
{
  "tool": "create_wall",
  "arguments": {
    "startPoint": [7000, 0, 0],
    "endPoint": [7000, 6000, 0],
    "height": 2800,
    "levelName": "Level 1",
    "wallTypeName": "Generic - 100mm"
  }
}
```

**Expected Result:** Interior walls dividing spaces

---

## Phase 4: Query Walls

### Test Filtering Tools

```json
// Test 17: Get all walls
{
  "tool": "get_elements_by_category",
  "arguments": {
    "category": "Walls"
  }
}

// Test 18: Get all elements (should include walls)
{
  "tool": "get_all_elements"
}

// Test 19: Find specific wall by ID (use ID from previous query)
{
  "tool": "get_element_by_id",
  "arguments": {
    "elementId": "12345"  // Replace with actual ID
  }
}
```

**Expected Result:** Should return all created walls with details

---

## Phase 5: Create Floors

### Test Floor Creation

```json
// Test 20: List available floor types
{
  "tool": "list_floor_types"
}

// Test 21: Create ground floor slab
{
  "tool": "create_floor",
  "arguments": {
    "boundary": [
      [0, 0, 0],
      [10000, 0, 0],
      [10000, 12000, 0],
      [0, 12000, 0]
    ],
    "levelName": "Level 1",
    "floorTypeName": "Generic - 150mm"
  }
}

// Test 22: Create first floor slab
{
  "tool": "create_floor",
  "arguments": {
    "boundary": [
      [0, 0, 3500],
      [10000, 0, 3500],
      [10000, 12000, 3500],
      [0, 12000, 3500]
    ],
    "levelName": "First Floor",
    "floorTypeName": "Generic - 150mm"
  }
}
```

**Expected Result:** 2 floor slabs created

---

## Phase 6: Place Doors

### Test Family Placement

```json
// Test 23: List available families
{
  "tool": "list_families"
}

// Test 24: List door families specifically
{
  "tool": "list_family_symbols",
  "arguments": {
    "familyName": "Single-Flush"  // Or whatever door family is available
  }
}

// Test 25: Place front door in south wall
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Single-Flush",
    "symbolName": "0915 x 2134mm",
    "location": [5000, 0, 0],
    "levelName": "Level 1"
  }
}

// Test 26: Place bedroom door 1
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Single-Flush",
    "symbolName": "0915 x 2134mm",
    "location": [3000, 3000, 0],
    "levelName": "Level 1"
  }
}

// Test 27: Place bedroom door 2
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Single-Flush",
    "symbolName": "0915 x 2134mm",
    "location": [3000, 9000, 0],
    "levelName": "Level 1"
  }
}

// Test 28: Place bathroom door
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Single-Flush",
    "symbolName": "0762 x 2134mm",
    "location": [7000, 3000, 0],
    "levelName": "Level 1"
  }
}
```

**Expected Result:** 4 doors placed in walls

---

## Phase 7: Place Windows

### Test Window Placement

```json
// Test 29: List window families
{
  "tool": "list_family_symbols",
  "arguments": {
    "familyName": "Fixed"  // Or whatever window family is available
  }
}

// Test 30: Place living room window 1
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Fixed",
    "symbolName": "1800 x 1200mm",
    "location": [1500, 0, 1000],
    "levelName": "Level 1"
  }
}

// Test 31: Place living room window 2
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Fixed",
    "symbolName": "1800 x 1200mm",
    "location": [8500, 0, 1000],
    "levelName": "Level 1"
  }
}

// Test 32: Place bedroom 1 window
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Fixed",
    "symbolName": "1200 x 1200mm",
    "location": [10000, 3000, 1000],
    "levelName": "Level 1"
  }
}

// Test 33: Place bedroom 2 window
{
  "tool": "place_family_instance",
  "arguments": {
    "familyName": "Fixed",
    "symbolName": "1200 x 1200mm",
    "location": [10000, 9000, 1000],
    "levelName": "Level 1"
  }
}
```

**Expected Result:** 4 windows placed in exterior walls

---

## Phase 8: Create Rooms

### Test Room Creation

```json
// Test 34: Create Living Room
{
  "tool": "create_room",
  "arguments": {
    "location": [1500, 6000, 0],
    "levelName": "Level 1",
    "name": "Living Room",
    "number": "101"
  }
}

// Test 35: Create Bedroom 1
{
  "tool": "create_room",
  "arguments": {
    "location": [6500, 3000, 0],
    "levelName": "Level 1",
    "name": "Bedroom 1",
    "number": "102"
  }
}

// Test 36: Create Bedroom 2
{
  "tool": "create_room",
  "arguments": {
    "location": [6500, 9000, 0],
    "levelName": "Level 1",
    "name": "Bedroom 2",
    "number": "103"
  }
}

// Test 37: Create Bathroom
{
  "tool": "create_room",
  "arguments": {
    "location": [8500, 3000, 0],
    "levelName": "Level 1",
    "name": "Bathroom",
    "number": "104"
  }
}

// Test 38: List all rooms
{
  "tool": "list_rooms"
}

// Test 39: Get room properties
{
  "tool": "room_properties",
  "arguments": {
    "roomId": "12345"  // Replace with actual room ID
  }
}
```

**Expected Result:** 4 rooms created with names and numbers

---

## Phase 9: Test Parameters

### Test Parameter Modification

```json
// Test 40: Get wall parameters (use wall ID from earlier)
{
  "tool": "get_parameters",
  "arguments": {
    "elementId": "12345"  // Replace with actual wall ID
  }
}

// Test 41: Set wall height parameter
{
  "tool": "set_parameter",
  "arguments": {
    "elementId": "12345",
    "parameterName": "Unconnected Height",
    "value": 3000
  }
}

// Test 42: Get room parameters
{
  "tool": "get_parameters",
  "arguments": {
    "elementId": "67890"  // Replace with actual room ID
  }
}

// Test 43: Set room name
{
  "tool": "set_parameter",
  "arguments": {
    "elementId": "67890",
    "parameterName": "Name",
    "value": "Master Bedroom"
  }
}
```

**Expected Result:** Parameters modified successfully

---

## Phase 10: Test Geometry & Location

### Test Geometry Tools

```json
// Test 44: Get wall geometry
{
  "tool": "get_geometry",
  "arguments": {
    "elementId": "12345"  // Replace with wall ID
  }
}

// Test 45: Get wall location
{
  "tool": "get_location",
  "arguments": {
    "elementId": "12345"
  }
}

// Test 46: Move a door
{
  "tool": "move_element",
  "arguments": {
    "elementId": "11111",  // Replace with door ID
    "translation": [500, 0, 0]  // Move 500mm in X direction
  }
}
```

**Expected Result:** Geometry data returned, element moved

---

## Phase 11: Test Materials

### Test Material Assignment

```json
// Test 47: List available materials
{
  "tool": "list_materials"
}

// Test 48: Assign material to wall
{
  "tool": "assign_material",
  "arguments": {
    "elementId": "12345",
    "materialName": "Concrete - Cast-in-Place Concrete"
  }
}
```

**Expected Result:** Material assigned to wall

---

## Phase 12: Advanced Queries

### Test Filtering & Search

```json
// Test 49: Get all doors
{
  "tool": "get_elements_by_category",
  "arguments": {
    "category": "Doors"
  }
}

// Test 50: Get all windows
{
  "tool": "get_elements_by_category",
  "arguments": {
    "category": "Windows"
  }
}

// Test 51: Get all floors
{
  "tool": "get_elements_by_category",
  "arguments": {
    "category": "Floors"
  }
}

// Test 52: Find elements (search)
{
  "tool": "find_elements",
  "arguments": {
    "searchTerm": "Living"
  }
}
```

**Expected Result:** Filtered element lists returned

---

## Phase 13: Save & Document

### Final Tests

```json
// Test 53: Save document
{
  "tool": "save_document"
}

// Test 54: Get final document info
{
  "tool": "get_document_info"
}

// Test 55: Get element count summary
{
  "tool": "get_all_elements"
}
```

**Expected Result:** Document saved, final summary

---

## Results Checklist

### Tools Tested:
- [ ] Document tools (list_documents, get_active_document, get_document_info)
- [ ] Level tools (list_levels, create_level)
- [ ] Wall tools (list_wall_types, create_wall, get_elements_by_category)
- [ ] Floor tools (list_floor_types, create_floor)
- [ ] Family tools (list_families, list_family_symbols, place_family_instance)
- [ ] Room tools (create_room, list_rooms, room_properties)
- [ ] Parameter tools (get_parameters, set_parameter)
- [ ] Geometry tools (get_geometry, get_location, move_element)
- [ ] Material tools (list_materials, assign_material)
- [ ] Query tools (find_elements, get_element_by_id, get_all_elements)
- [ ] Save tools (save_document)

### Villa Components Created:
- [ ] 3 Levels (Level 1, First Floor, Roof)
- [ ] 7 Walls (4 external + 3 internal)
- [ ] 2 Floor slabs
- [ ] 4 Doors
- [ ] 4 Windows
- [ ] 4 Rooms with names

### Issues Found:
*(Document any errors or problems below)*

---

## Success Criteria

✅ **Full Success:** All 55 tests pass, complete villa created
⚠️ **Partial Success:** 80%+ tests pass, most features work
❌ **Failure:** <80% tests pass, major features broken

**Total Tests: 55**
**Tests Passed: ___**
**Tests Failed: ___**
**Success Rate: ___%**

---

**Ready to start testing! Use Claude Desktop or your MCP client to run these commands sequentially.**
