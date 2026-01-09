"""
Comprehensive Test Suite for ALL Revit MCP Tools
Tests all 103 available tools systematically
"""

import requests
import json
import time

URL = "http://localhost:3000/execute"

class ToolTester:
    def __init__(self):
        self.counter = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.results = []

    def test(self, tool, payload={}, skip_reason=None):
        self.counter += 1

        if skip_reason:
            print(f"\n[Test {self.counter}] {tool} - SKIPPED: {skip_reason}")
            self.skipped += 1
            self.results.append({"test": self.counter, "tool": tool, "status": "SKIPPED", "reason": skip_reason})
            return None

        print(f"\n[Test {self.counter}] {tool}")
        print("-" * 60)

        try:
            r = requests.post(URL, json={
                "request_id": f"test-{self.counter}",
                "tool": tool,
                "payload": payload
            }, timeout=30)

            result = r.json()

            if result.get("Status") == "ok":
                print(f"PASS - {tool}")
                self.passed += 1
                self.results.append({"test": self.counter, "tool": tool, "status": "PASS", "result": result.get("Result")})
                return result.get("Result")
            else:
                print(f"FAIL - {tool}")
                print(f"Error: {result.get('Message', 'Unknown error')}")
                self.failed += 1
                self.results.append({"test": self.counter, "tool": tool, "status": "FAIL", "error": result.get("Message")})
                return None

        except Exception as e:
            print(f"EXCEPTION - {str(e)}")
            self.failed += 1
            self.results.append({"test": self.counter, "tool": tool, "status": "EXCEPTION", "error": str(e)})
            return None

    def summary(self):
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Total Tests: {self.counter}")
        print(f"Passed: {self.passed} ({self.passed/self.counter*100:.1f}%)")
        print(f"Failed: {self.failed} ({self.failed/self.counter*100:.1f}%)")
        print(f"Skipped: {self.skipped} ({self.skipped/self.counter*100:.1f}%)")
        print("="*60)

        # Save results
        with open("test_all_results.json", "w") as f:
            json.dump(self.results, f, indent=2)
        print("\nDetailed results saved to: test_all_results.json")

tester = ToolTester()

print("="*60)
print("COMPREHENSIVE REVIT MCP TOOL TEST SUITE")
print("Testing ALL 103 Available Tools")
print("="*60)

# Store element IDs for later tests
created_elements = {}

# =============================================================================
# CATEGORY 1: HEALTH & SERVER
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 1: HEALTH & SERVER (1 tool)")
print("="*60)

tester.test("revit.health")

# =============================================================================
# CATEGORY 2: DOCUMENT MANAGEMENT
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 2: DOCUMENT MANAGEMENT (4 tools)")
print("="*60)

tester.test("revit.get_document_info")
tester.test("revit.list_views")
tester.test("revit.save_document", skip_reason="Document not saved to disk yet")
tester.test("revit.close_document", skip_reason="Would close active document")
tester.test("revit.create_new_document", skip_reason="Would replace current document")
tester.test("revit.open_document", skip_reason="Requires file path")

# =============================================================================
# CATEGORY 3: LEVELS & GRIDS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 3: LEVELS & GRIDS (3 tools)")
print("="*60)

levels = tester.test("revit.list_levels")

# Create test levels if not exists
result = tester.test("revit.create_level", {"name": "Test Level 5m", "elevation": 5000})
if result:
    created_elements['level'] = result.get('level_id')

result = tester.test("revit.create_grid", {
    "start_point": [0, 0, 0],
    "end_point": [10000, 0, 0],
    "name": "Grid A"
})
if result:
    created_elements['grid'] = result.get('grid_id')

# =============================================================================
# CATEGORY 4: WALLS, FLOORS, ROOFS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 4: WALLS, FLOORS, ROOFS (3 tools)")
print("="*60)

# Already tested walls in basic test
result = tester.test("revit.create_wall", {
    "start_point": [15000, 0, 0],
    "end_point": [15000, 5000, 0],
    "height": 3000,
    "level": "L1"
})
if result:
    created_elements['wall'] = result.get('wall_id')

result = tester.test("revit.create_floor", {
    "boundary_points": [
        [15000, 0, 0],
        [20000, 0, 0],
        [20000, 5000, 0],
        [15000, 5000, 0]
    ],
    "level": "L1"
})
if result:
    created_elements['floor'] = result.get('floor_id')

result = tester.test("revit.create_roof", {
    "boundary_points": [
        [15000, 0, 5000],
        [20000, 0, 5000],
        [20000, 5000, 5000],
        [15000, 5000, 5000]
    ],
    "level": "L1"
})
if result:
    created_elements['roof'] = result.get('roof_id')

# =============================================================================
# CATEGORY 5: ROOMS & SPACES
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 5: ROOMS & SPACES (1 tool)")
print("="*60)

result = tester.test("revit.create_room", {
    "location_point": [17500, 2500, 0],
    "level": "L1",
    "name": "Test Room",
    "number": "999"
})
if result:
    created_elements['room'] = result.get('room_id')

# =============================================================================
# CATEGORY 6: FAMILIES & COMPONENTS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 6: FAMILIES & COMPONENTS (4 tools)")
print("="*60)

families = tester.test("revit.list_families")

tester.test("revit.place_family_instance", skip_reason="Requires loaded family name")
tester.test("revit.place_door", skip_reason="Requires wall with opening")
tester.test("revit.place_window", skip_reason="Requires wall with opening")
tester.test("revit.edit_family", skip_reason="Requires family document")

# =============================================================================
# CATEGORY 7: STRUCTURAL ELEMENTS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 7: STRUCTURAL ELEMENTS (3 tools)")
print("="*60)

result = tester.test("revit.create_column", {
    "location_point": [25000, 0, 0],
    "level": "L1",
    "height": 3000
})
if result:
    created_elements['column'] = result.get('column_id')

result = tester.test("revit.create_beam", {
    "start_point": [25000, 0, 3000],
    "end_point": [30000, 0, 3000],
    "level": "L1"
})
if result:
    created_elements['beam'] = result.get('beam_id')

result = tester.test("revit.create_foundation", {
    "boundary_points": [
        [25000, 0, -500],
        [30000, 0, -500],
        [30000, 5000, -500],
        [25000, 5000, -500]
    ],
    "level": "L1"
})
if result:
    created_elements['foundation'] = result.get('foundation_id')

# =============================================================================
# CATEGORY 8: MEP SYSTEMS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 8: MEP SYSTEMS (5 tools)")
print("="*60)

result = tester.test("revit.create_duct", {
    "start_point": [0, 15000, 3000],
    "end_point": [5000, 15000, 3000],
    "diameter": 300,
    "level": "L1"
})
if result:
    created_elements['duct'] = result.get('duct_id')

result = tester.test("revit.create_pipe", {
    "start_point": [0, 16000, 2000],
    "end_point": [5000, 16000, 2000],
    "diameter": 100,
    "level": "L1"
})
if result:
    created_elements['pipe'] = result.get('pipe_id')

result = tester.test("revit.create_cable_tray", {
    "start_point": [0, 17000, 3500],
    "end_point": [5000, 17000, 3500],
    "width": 300,
    "height": 100,
    "level": "L1"
})
if result:
    created_elements['cable_tray'] = result.get('cable_tray_id')

result = tester.test("revit.create_conduit", {
    "start_point": [0, 18000, 3500],
    "end_point": [5000, 18000, 3500],
    "diameter": 50,
    "level": "L1"
})
if result:
    created_elements['conduit'] = result.get('conduit_id')

tester.test("revit.get_mep_systems")

# =============================================================================
# CATEGORY 9: ELEMENT QUERIES
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 9: ELEMENT QUERIES (6 tools)")
print("="*60)

tester.test("revit.list_elements_by_category", {"category": "Walls"})
tester.test("revit.list_elements_by_category", {"category": "Floors"})
tester.test("revit.list_elements_by_category", {"category": "Rooms"})
tester.test("revit.get_categories")

if created_elements.get('wall'):
    tester.test("revit.get_element_type", {"element_id": created_elements['wall']})
    tester.test("revit.get_element_bounding_box", {"element_id": created_elements['wall']})

# =============================================================================
# CATEGORY 10: ELEMENT OPERATIONS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 10: ELEMENT OPERATIONS (8 tools)")
print("="*60)

tester.test("revit.get_selection")
tester.test("revit.set_selection", skip_reason="Requires element IDs")

if created_elements.get('wall'):
    wall_id = created_elements['wall']

    # Test move
    result = tester.test("revit.move_element", {
        "element_id": wall_id,
        "translation": [100, 0, 0]
    })

    # Test copy
    result = tester.test("revit.copy_element", {
        "element_id": wall_id,
        "translation": [0, 1000, 0]
    })
    if result:
        copied_id = result.get('new_element_id')

        # Test rotate
        tester.test("revit.rotate_element", {
            "element_id": copied_id,
            "angle": 45,
            "axis_origin": [15000, 0, 0],
            "axis_direction": [0, 0, 1]
        })

        # Test mirror
        tester.test("revit.mirror_element", {
            "element_id": copied_id,
            "plane_origin": [15000, 0, 0],
            "plane_normal": [1, 0, 0]
        })

        # Test pin/unpin
        tester.test("revit.pin_element", {"element_id": copied_id})
        tester.test("revit.unpin_element", {"element_id": copied_id})

        # Test delete
        tester.test("revit.delete_element", {"element_id": copied_id})

# =============================================================================
# CATEGORY 11: PARAMETERS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 11: PARAMETERS (10 tools)")
print("="*60)

if created_elements.get('wall'):
    wall_id = created_elements['wall']

    params = tester.test("revit.get_element_parameters", {"element_id": wall_id})

    if params and len(params.get('parameters', [])) > 0:
        first_param = params['parameters'][0]
        param_name = first_param.get('name')

        tester.test("revit.get_parameter_value", {
            "element_id": wall_id,
            "parameter_name": param_name
        })

        # Try to set a parameter (might fail if read-only)
        tester.test("revit.set_parameter_value", {
            "element_id": wall_id,
            "parameter_name": "Comments",
            "value": "Test comment"
        })

tester.test("revit.list_shared_parameters")
tester.test("revit.list_project_parameters")
tester.test("revit.create_shared_parameter", skip_reason="Requires shared parameter file")
tester.test("revit.create_project_parameter", skip_reason="Requires parameter definition")
tester.test("revit.batch_set_parameters", skip_reason="Requires element list")

if created_elements.get('wall'):
    tester.test("revit.get_type_parameters", {"element_id": created_elements['wall']})
    tester.test("revit.set_type_parameter", skip_reason="Requires type parameter name")

# =============================================================================
# CATEGORY 12: VIEWS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 12: VIEWS (5 tools)")
print("="*60)

result = tester.test("revit.create_floor_plan_view", {"level": "L1", "name": "Test Floor Plan"})
if result:
    created_elements['floor_plan'] = result.get('view_id')

result = tester.test("revit.create_3d_view", {"name": "Test 3D View"})
if result:
    created_elements['3d_view'] = result.get('view_id')

result = tester.test("revit.create_section_view", {
    "start_point": [0, 0, 0],
    "end_point": [10000, 0, 0],
    "view_direction": [0, 1, 0],
    "name": "Test Section"
})
if result:
    created_elements['section'] = result.get('view_id')

tester.test("revit.get_view_templates")
tester.test("revit.apply_view_template", skip_reason="Requires view and template IDs")

# =============================================================================
# CATEGORY 13: SHEETS & DOCUMENTATION
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 13: SHEETS & DOCUMENTATION (10 tools)")
print("="*60)

tester.test("revit.list_sheets")
tester.test("revit.list_titleblocks")

result = tester.test("revit.create_sheet", {
    "number": "A999",
    "name": "Test Sheet"
})
if result:
    sheet_id = result.get('sheet_id')
    created_elements['sheet'] = sheet_id

    tester.test("revit.get_sheet_info", {"sheet_id": sheet_id})

    if created_elements.get('floor_plan'):
        tester.test("revit.place_viewport_on_sheet", {
            "sheet_id": sheet_id,
            "view_id": created_elements['floor_plan'],
            "location": [0.5, 0.5]
        })

    tester.test("revit.populate_titleblock", {
        "sheet_id": sheet_id,
        "parameters": {
            "Project Name": "Test Project",
            "Sheet Title": "Test Sheet Title"
        }
    })

    result = tester.test("revit.duplicate_sheet", {"sheet_id": sheet_id})
    if result:
        dup_sheet_id = result.get('new_sheet_id')
        tester.test("revit.delete_sheet", {"sheet_id": dup_sheet_id})

tester.test("revit.renumber_sheets", skip_reason="Would renumber all sheets")
tester.test("revit.batch_create_sheets_from_csv", skip_reason="Requires CSV file")

# =============================================================================
# CATEGORY 14: ANNOTATION
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 14: ANNOTATION (6 tools)")
print("="*60)

if created_elements.get('floor_plan'):
    view_id = created_elements['floor_plan']

    result = tester.test("revit.create_text_note", {
        "view_id": view_id,
        "location": [5000, 5000, 0],
        "text": "Test Note"
    })

    tester.test("revit.create_text_type", skip_reason="Requires text type definition")

    if created_elements.get('wall'):
        tester.test("revit.create_tag", {
            "view_id": view_id,
            "element_id": created_elements['wall'],
            "location": [15000, 2500, 0]
        })

    tester.test("revit.create_dimension", skip_reason="Requires reference array")
    tester.test("revit.create_revision_cloud", skip_reason="Requires sketch curves")
    tester.test("revit.tag_all_in_view", {"view_id": view_id})

tester.test("revit.get_revision_sequences")

# =============================================================================
# CATEGORY 15: SCHEDULES
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 15: SCHEDULES (3 tools)")
print("="*60)

result = tester.test("revit.create_schedule", {
    "category": "Walls",
    "name": "Test Wall Schedule"
})
if result:
    schedule_id = result.get('schedule_id')
    tester.test("revit.get_schedule_data", {"schedule_id": schedule_id})

tester.test("revit.export_schedules", skip_reason="Requires output path")

# =============================================================================
# CATEGORY 16: EXPORTS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 16: EXPORTS (5 tools)")
print("="*60)

tester.test("revit.export_pdf_by_sheet_set", skip_reason="Requires sheet IDs and output path")
tester.test("revit.export_dwg_by_view", skip_reason="Requires view ID and output path")
tester.test("revit.export_ifc_with_settings", skip_reason="Requires output path")
tester.test("revit.export_navisworks", skip_reason="Requires output path")
tester.test("revit.export_image", skip_reason="Requires view ID and output path")
tester.test("revit.render_3d_view", skip_reason="Requires 3D view and long processing time")

# =============================================================================
# CATEGORY 17: MATERIALS & RENDERING
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 17: MATERIALS & RENDERING (4 tools)")
print("="*60)

result = tester.test("revit.create_material", {"name": "Test Material"})
if result and created_elements.get('wall'):
    material_id = result.get('material_id')
    tester.test("revit.set_element_material", {
        "element_id": created_elements['wall'],
        "material_id": material_id
    })

tester.test("revit.get_render_settings")
tester.test("revit.calculate_material_quantities")

# =============================================================================
# CATEGORY 18: GROUPS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 18: GROUPS (4 tools)")
print("="*60)

if created_elements.get('wall') and created_elements.get('floor'):
    result = tester.test("revit.create_group", {
        "element_ids": [created_elements['wall'], created_elements['floor']],
        "name": "Test Group"
    })
    if result:
        group_id = result.get('group_id')
        created_elements['group'] = group_id

        tester.test("revit.get_group_members", {"group_id": group_id})
        tester.test("revit.ungroup", {"group_id": group_id})

tester.test("revit.convert_to_group", skip_reason="Requires element IDs")

# =============================================================================
# CATEGORY 19: WORKSETS & WORKSHARING
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 19: WORKSETS & WORKSHARING (3 tools)")
print("="*60)

tester.test("revit.get_worksets")
tester.test("revit.sync_to_central", skip_reason="Not a workshared document")
tester.test("revit.relinquish_all", skip_reason="Not a workshared document")

# =============================================================================
# CATEGORY 20: LINKS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 20: LINKS (2 tools)")
print("="*60)

tester.test("revit.get_rvt_links")
tester.test("revit.get_link_instances")

# =============================================================================
# CATEGORY 21: PHASES & DESIGN OPTIONS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 21: PHASES & DESIGN OPTIONS (3 tools)")
print("="*60)

tester.test("revit.get_phases")
tester.test("revit.get_phase_filters")
tester.test("revit.get_design_options")

# =============================================================================
# CATEGORY 22: PROJECT SETTINGS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 22: PROJECT SETTINGS (3 tools)")
print("="*60)

tester.test("revit.get_project_location")
tester.test("revit.get_warnings")

if created_elements.get('room'):
    tester.test("revit.get_room_boundary", {"room_id": created_elements['room']})

# =============================================================================
# CATEGORY 23: CLASHES & ANALYSIS
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 23: CLASHES & ANALYSIS (1 tool)")
print("="*60)

tester.test("revit.check_clashes", skip_reason="Requires element ID arrays")

# =============================================================================
# CATEGORY 24: REFLECTION API (ADVANCED)
# =============================================================================
print("\n" + "="*60)
print("CATEGORY 24: REFLECTION API (3 tools)")
print("="*60)

tester.test("revit.invoke_method", skip_reason="Requires method signature")
tester.test("revit.reflect_get", skip_reason="Requires object and property path")
tester.test("revit.reflect_set", skip_reason="Requires object and property path")

# =============================================================================
# FINAL SUMMARY
# =============================================================================
tester.summary()

print("\n" + "="*60)
print("ELEMENTS CREATED DURING TESTING:")
print("="*60)
for key, value in created_elements.items():
    print(f"{key}: {value}")
