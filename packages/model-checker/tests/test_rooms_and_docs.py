"""Test room and documentation validation (Scaffolds 6 & 7)."""

from model_checker.rooms import DocumentationValidator, RoomValidator


# SCAFFOLD 6 TESTS: Rooms

def test_validate_room_boundaries():
    """Test room boundary validation."""
    validator = RoomValidator()

    rooms = [
        {"id": "room_1", "name": "Office 1", "is_bound": True},
        {"id": "room_2", "name": "Office 2", "is_bound": False},  # Unbound
        {"id": "room_3", "name": "Office 3", "is_bound": True, "overlaps_with": "room_1"},  # Overlapping
    ]

    issues = validator.validate_room_boundaries(rooms)
    assert len(issues) == 2  # 1 unbound + 1 overlapping


def test_validate_room_areas():
    """Test room area validation."""
    validator = RoomValidator()

    rooms = [
        {"id": "room_1", "area": 3.0},  # Too small
        {"id": "room_2", "area": 600.0},  # Too large
        {"id": "room_3", "area": 50.0, "required_area": 60.0},  # Mismatch (>10%)
        {"id": "room_4", "area": 100.0, "required_area": 105.0},  # OK (within 10%)
    ]

    issues = validator.validate_room_areas(rooms, min_area=5.0, max_area=500.0)
    assert len(issues) == 3  # Too small, too large, mismatch


def test_validate_occupancy():
    """Test occupancy and egress validation."""
    validator = RoomValidator()

    rooms = [
        {"id": "room_1", "area": 100.0, "has_exit_access": True, "exit_width": 1500},  # OK
        {"id": "room_2", "area": 50.0, "has_exit_access": False, "exit_width": 0},  # No exit
        {"id": "room_3", "area": 200.0, "has_exit_access": True, "exit_width": 900},  # Insufficient width
    ]

    issues = validator.validate_occupancy(rooms, max_occupant_load_factor=10.0)
    assert len(issues) >= 2  # No exit + insufficient width


# SCAFFOLD 7 TESTS: Documentation

def test_validate_view_coverage():
    """Test view coverage validation."""
    validator = DocumentationValidator()

    views = [
        {"id": "view_1", "type": "floor_plan"},
        {"id": "view_2", "type": "section"},
    ]

    elements = [
        {"id": "elem_1", "type": "wall", "visible_in_views": ["view_1"], "required_view_types": ["floor_plan"]},  # OK
        {"id": "elem_2", "type": "beam", "visible_in_views": [], "required_view_types": ["floor_plan"]},  # Missing
    ]

    issues = validator.validate_view_coverage(elements, views)
    assert len(issues) == 1  # elem_2 not in floor plan


def test_validate_sheets():
    """Test sheet validation."""
    validator = DocumentationValidator()

    sheets = [
        {"id": "sheet_1", "number": "A-101", "has_titleblock": True, "viewports": ["vp_1"]},  # OK
        {"id": "sheet_2", "number": "A-102", "has_titleblock": False, "viewports": []},  # No titleblock, no views
        {"id": "sheet_3", "number": "A-103", "has_titleblock": True, "viewports": []},  # No views
    ]

    issues = validator.validate_sheets(sheets)
    assert len(issues) == 3  # sheet_2: 2 issues, sheet_3: 1 issue


def test_validate_revisions():
    """Test revision tracking validation."""
    validator = DocumentationValidator()

    revisions = [
        {"id": "rev_1", "description": "Initial Issue"},
        {"id": "rev_2", "description": "Design Development"},
    ]

    sheets = [
        {"id": "sheet_1", "revisions": ["rev_1"], "has_revision_clouds": True},  # OK
        {"id": "sheet_2", "revisions": ["rev_999"], "has_revision_clouds": False},  # Invalid revision
        {"id": "sheet_3", "revisions": ["rev_2"], "has_revision_clouds": False},  # Missing clouds
    ]

    issues = validator.validate_revisions(sheets, revisions)
    assert len(issues) == 3  # sheet_2: invalid revision + missing clouds, sheet_3: missing clouds


def test_complete_room_workflow():
    """Test complete room validation workflow."""
    validator = RoomValidator()

    rooms = [
        {"id": "office_1", "name": "Office", "is_bound": True, "area": 25.0, "has_exit_access": True, "exit_width": 900},
        {"id": "conf_1", "name": "Conference", "is_bound": False, "area": 2.0, "has_exit_access": False, "exit_width": 0},
    ]

    validator.validate_room_boundaries(rooms)
    validator.validate_room_areas(rooms, min_area=5.0)
    validator.validate_occupancy(rooms)

    issues = validator.get_issues()
    assert len(issues) >= 3  # Unbound, too small area, no exit


def test_complete_documentation_workflow():
    """Test complete documentation validation workflow."""
    validator = DocumentationValidator()

    views = [{"id": "view_1", "type": "floor_plan"}]
    elements = [{"id": "elem_1", "visible_in_views": [], "required_view_types": ["floor_plan"]}]
    sheets = [{"id": "sheet_1", "number": "A-101", "has_titleblock": False, "viewports": []}]
    revisions = []

    validator.validate_view_coverage(elements, views)
    validator.validate_sheets(sheets)
    validator.validate_revisions(sheets, revisions)

    issues = validator.get_issues()
    assert len(issues) >= 3  # Missing from view + no titleblock + no views
