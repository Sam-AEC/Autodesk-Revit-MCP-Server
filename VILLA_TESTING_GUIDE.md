# Villa Testing Guide - RevitMCP Bridge

**Date:** 2026-01-08
**Purpose:** Comprehensive testing of modern UI and available tools by building a villa

---

## 🎯 Testing Objectives

1. **Verify Modern UI** - Confirm all dialogs display with professional styling
2. **Test Core Commands** - Verify Connect, Disconnect, Status work correctly
3. **Build Villa** - Use available tools to create a complete villa model
4. **Document Issues** - Record any errors or functionality problems

---

## ✅ Phase 1: UI Testing (FIRST - Before opening Revit)

### Prerequisites
- ✅ Modern UI committed to git
- ✅ Built successfully (0 errors)
- ✅ .addin file points to new DLL
- ⚠️ **IMPORTANT:** Restart Revit if it was open during build

### UI Test Steps

1. **Start Revit 2024**
   - Look for "RevitMCP" tab in ribbon
   - Should see professional icons (not just text)

2. **Test Connect Button** (🟢 Green Play Icon)
   - Click "Connect"
   - **Expected:** Modern dialog with:
     - Blue gradient header
     - Green checkmark status card
     - "Server Connected" message
     - Professional styling with shadows
   - **Not Expected:** Basic Windows TaskDialog

3. **Test Status Button** (📊 Blue Chart Icon)
   - Click "Status"
   - **Expected:** Modern dialog showing:
     - Server statistics (tools, coverage, commands)
     - Status cards with icons
     - Request count and active connections
     - Professional layout

4. **Test Settings Button** (⚙️ Gray Gear Icon)
   - Click "Settings"
   - **Expected:** Configuration dialog showing:
     - Port: 3000
     - Host: localhost
     - Feature list with checkmarks
     - Config file location

5. **Test Help Button** (❓ Info Icon)
   - Click "Help"
   - **Expected:** Documentation dialog with:
     - Quick start guide
     - Available commands list
     - GitHub link button
     - Stats grid

6. **Test Disconnect Button** (🔴 Red Stop Icon)
   - Click "Disconnect"
   - **Expected:** Modern dialog confirming stop
   - Server should stop gracefully

---

## 🏗️ Phase 2: Villa Creation Testing

### Available Tools (90 tools ready to test)

The Phase 1-4 commands (143 tools) are temporarily excluded, but we have **90 working tools** from the base implementation.

### Tool Categories to Test:

#### 1. **Document & Project Tools**
- `list_documents` - List open documents
- `get_active_document` - Get current active document
- `get_document_info` - Get document metadata
- `save_document` - Save current document

#### 2. **Element Selection & Filtering**
- `get_all_elements` - Get all elements in document
- `get_elements_by_category` - Filter by category
- `get_element_by_id` - Get specific element
- `find_elements` - Search elements

#### 3. **Levels & Views**
- `list_levels` - Get all levels
- `create_level` - Create new level
- `list_views` - Get all views
- `create_view` - Create new view

#### 4. **Walls**
- `create_wall` - Create wall by points
- `list_wall_types` - Get available wall types
- `modify_wall` - Change wall properties

#### 5. **Floors**
- `create_floor` - Create floor by boundary
- `list_floor_types` - Get floor types

#### 6. **Families & Types**
- `list_families` - Get loaded families
- `list_family_symbols` - Get family types
- `place_family_instance` - Place family (doors, windows, furniture)

#### 7. **Parameters**
- `get_parameters` - Get element parameters
- `set_parameter` - Modify parameter value
- `list_shared_parameters` - Get shared parameters

#### 8. **Geometry**
- `get_geometry` - Get element geometry
- `get_location` - Get element location
- `move_element` - Move element to new position

#### 9. **Rooms & Spaces**
- `create_room` - Create room
- `list_rooms` - Get all rooms
- `room_properties` - Get room details

#### 10. **Materials**
- `list_materials` - Get available materials
- `assign_material` - Apply material to element

---

## 🏡 Villa Building Test Sequence

### Step 1: Project Setup
```
Test: Create new Revit project
1. File > New > Architectural Template
2. Save as "TestVilla_2026-01-08.rvt"

Test MCP: list_documents
Test MCP: get_document_info
```

### Step 2: Create Levels
```
Test: Create building levels
1. Use list_levels to see existing levels
2. Create ground floor (elevation 0)
3. Create first floor (elevation 3500mm)
4. Create roof level (elevation 7000mm)

MCP Commands:
- list_levels
- create_level (name: "First Floor", elevation: 3500)
- create_level (name: "Roof", elevation: 7000)
```

### Step 3: Create External Walls
```
Test: Create villa perimeter walls
1. Switch to ground floor plan view
2. Create rectangular perimeter (10m x 12m)
3. Use create_wall with wall type and points

MCP Commands:
- list_views (find ground floor plan)
- list_wall_types (choose exterior wall)
- create_wall (4 walls forming rectangle)

Points example:
- Wall 1: (0,0) to (12000,0)
- Wall 2: (12000,0) to (12000,10000)
- Wall 3: (12000,10000) to (0,10000)
- Wall 4: (0,10000) to (0,0)
```

### Step 4: Create Internal Walls
```
Test: Divide interior spaces
1. Create walls for rooms (living, kitchen, bedrooms, bathroom)
2. Test wall type variations

MCP Commands:
- list_wall_types (choose interior partition)
- create_wall (multiple interior walls)
```

### Step 5: Add Floors
```
Test: Create floor slabs
1. Create ground floor slab
2. Create first floor slab

MCP Commands:
- list_floor_types
- create_floor (boundary matching exterior walls)
```

### Step 6: Place Doors
```
Test: Add doors to villa
1. List available door families
2. Place external door (front entrance)
3. Place internal doors (room connections)

MCP Commands:
- list_families (filter: "Doors")
- list_family_symbols (get door types)
- place_family_instance (place each door in walls)

Doors to place:
- 1x External front door (1000mm)
- 3x Internal doors (900mm) - bedrooms
- 2x Internal doors (800mm) - bathroom, closet
```

### Step 7: Place Windows
```
Test: Add windows for natural light
1. List window families
2. Place windows in exterior walls

MCP Commands:
- list_families (filter: "Windows")
- list_family_symbols
- place_family_instance (place windows)

Windows to place:
- Living room: 2x large windows (1800x1200)
- Bedrooms: 1x window each (1200x1200)
- Kitchen: 1x window (1000x1000)
- Bathroom: 1x small window (600x600)
```

### Step 8: Create Roof
```
Test: Add roof structure
Note: Basic roof tools might be limited without Phase commands

Try:
- Manual roof creation in Revit UI
- Document if roof commands are available via MCP
```

### Step 9: Create Rooms
```
Test: Define room boundaries and properties
1. Create rooms in each space
2. Set room names and numbers

MCP Commands:
- create_room (place in each bounded area)
- set_parameter (set room name, number)

Rooms to create:
- Living Room (30 m²)
- Kitchen (15 m²)
- Master Bedroom (20 m²)
- Bedroom 2 (15 m²)
- Bedroom 3 (12 m²)
- Bathroom (8 m²)
- Hallway (10 m²)
```

### Step 10: Test Parameter Modification
```
Test: Modify element properties
1. Select a wall
2. Change height parameter
3. Change material

MCP Commands:
- get_element_by_id
- get_parameters (see available parameters)
- set_parameter (modify values)

Test modifications:
- Change wall height to 2800mm
- Change wall type
- Modify room names
- Update door widths
```

### Step 11: Test Filtering & Queries
```
Test: Query and filter elements
1. Get all walls in project
2. Filter doors by size
3. Find all rooms

MCP Commands:
- get_all_elements
- get_elements_by_category (category: "Walls")
- get_elements_by_category (category: "Doors")
- list_rooms
```

### Step 12: Test Geometry & Location
```
Test: Get element geometry data
1. Get wall geometry
2. Get element locations
3. Test move element

MCP Commands:
- get_geometry (wall or floor)
- get_location (any element)
- move_element (shift element position)
```

### Step 13: Materials Testing
```
Test: Material assignment
1. List available materials
2. Assign materials to walls
3. Change floor materials

MCP Commands:
- list_materials
- assign_material (apply to walls/floors)
```

---

## 📊 Results Documentation

### Success Criteria

✅ **UI Tests Pass**
- [ ] Modern dialogs display correctly
- [ ] Icons appear in ribbon
- [ ] All buttons functional
- [ ] Professional styling visible

✅ **Villa Creation Complete**
- [ ] All walls created successfully
- [ ] Floors added
- [ ] Doors and windows placed
- [ ] Rooms defined
- [ ] Parameters modified

✅ **Tool Coverage**
- [ ] 90+ tools tested
- [ ] No critical errors
- [ ] Performance acceptable
- [ ] Commands return expected results

---

## 🐛 Issue Tracking Template

For each issue found, document:

```markdown
### Issue: [Brief Description]
- **Tool/Command:** `command_name`
- **Expected:** What should happen
- **Actual:** What actually happened
- **Error Message:** Copy any error text
- **Steps to Reproduce:**
  1. Step 1
  2. Step 2
  3. Step 3
- **Severity:** Critical / High / Medium / Low
- **Workaround:** If any exists
```

---

## 🚀 Getting Started

1. **Commit Check:** ✅ Modern UI committed (commit 636447c)
2. **Build Check:** ✅ Build successful (0 errors)
3. **Revit Restart:** ⚠️ **Close and restart Revit now**
4. **Begin Testing:** Start with Phase 1 UI tests
5. **Document Results:** Keep notes of all findings

---

## 💡 Tips

- **Take Screenshots:** Capture modern dialogs for documentation
- **Save Frequently:** Save villa project after each major step
- **Test Incrementally:** Don't rush, test one category at a time
- **Note Performance:** Track how long operations take
- **Check Logs:** Review logs at `%AppData%\RevitMCP\Logs\bridge.jsonl`

---

## 📝 Next Steps After Testing

Based on test results:

1. **If UI works perfectly:** Continue to villa building tests
2. **If errors occur:** Document and fix critical issues first
3. **After villa complete:** Consider re-enabling Phase 1-4 commands
4. **Performance issues:** Optimize specific slow operations

---

**Ready to start testing? Close Revit if it's open, restart it, and begin with Phase 1! 🎉**
