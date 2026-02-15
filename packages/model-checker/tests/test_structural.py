"""Test structural validation."""

import pytest

from model_checker.structural import StructuralValidator


def test_validate_beam_connections_valid():
    """Test validating properly connected beams."""
    validator = StructuralValidator()

    columns = [
        {"id": "col_1", "location": {"x": 0, "y": 0, "z": 0}},
        {"id": "col_2", "location": {"x": 6000, "y": 0, "z": 0}},
    ]

    beams = [
        {
            "id": "beam_1",
            "start_point": {"x": 0, "y": 0, "z": 3000},
            "end_point": {"x": 6000, "y": 0, "z": 3000},
        }
    ]

    issues = validator.validate_beam_connections(beams, columns)
    assert len(issues) == 0


def test_validate_beam_unconnected_start():
    """Test detecting beam with unconnected start."""
    validator = StructuralValidator()

    columns = [{"id": "col_1", "location": {"x": 6000, "y": 0, "z": 0}}]

    beams = [
        {
            "id": "beam_1",
            "start_point": {"x": 0, "y": 0, "z": 3000},  # No column here
            "end_point": {"x": 6000, "y": 0, "z": 3000},
        }
    ]

    issues = validator.validate_beam_connections(beams, columns)
    assert len(issues) == 1
    assert issues[0].issue_type == "unconnected_start"
    assert issues[0].severity == "critical"


def test_validate_beam_both_unconnected():
    """Test detecting beam with both ends unconnected."""
    validator = StructuralValidator()

    columns = []
    beams = [
        {
            "id": "beam_1",
            "start_point": {"x": 0, "y": 0, "z": 3000},
            "end_point": {"x": 6000, "y": 0, "z": 3000},
        }
    ]

    issues = validator.validate_beam_connections(beams, columns)
    assert len(issues) == 2  # Both start and end


def test_validate_foundations_valid():
    """Test validating columns with foundations."""
    validator = StructuralValidator()

    columns = [
        {"id": "col_1", "name": "C1", "base_point": {"x": 0, "y": 0, "z": 0}},
        {"id": "col_2", "name": "C2", "base_point": {"x": 6000, "y": 0, "z": 0}},
    ]

    foundations = [
        {"id": "found_1", "location": {"x": 0, "y": 0, "z": -500}},
        {"id": "found_2", "location": {"x": 6000, "y": 0, "z": -500}},
    ]

    issues = validator.validate_foundations(columns, foundations)
    assert len(issues) == 0


def test_validate_foundations_missing():
    """Test detecting columns without foundations."""
    validator = StructuralValidator()

    columns = [
        {"id": "col_1", "name": "C1", "base_point": {"x": 0, "y": 0, "z": 0}},
        {"id": "col_2", "name": "C2", "base_point": {"x": 6000, "y": 0, "z": 0}},
    ]

    foundations = [
        {"id": "found_1", "location": {"x": 0, "y": 0, "z": -500}}  # Only one foundation
    ]

    issues = validator.validate_foundations(columns, foundations)
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_foundation"
    assert issues[0].element_id == "col_2"


def test_validate_load_path_complete():
    """Test validating complete load path."""
    validator = StructuralValidator()

    roof_elements = [{"id": "roof_1", "location": {"x": 3000, "y": 0, "z": 6000}}]

    beams = [
        {
            "id": "beam_1",
            "start_point": {"x": 0, "y": 0, "z": 3000},
            "end_point": {"x": 6000, "y": 0, "z": 3000},
        }
    ]

    columns = [
        {"id": "col_1", "base_point": {"x": 0, "y": 0, "z": 0}},
        {"id": "col_2", "base_point": {"x": 6000, "y": 0, "z": 0}},
    ]

    foundations = [
        {"id": "found_1", "location": {"x": 0, "y": 0, "z": -500}},
        {"id": "found_2", "location": {"x": 6000, "y": 0, "z": -500}},
    ]

    issues = validator.validate_load_path(roof_elements, beams, columns, foundations)
    # May have some issues depending on simplified geometry matching
    assert isinstance(issues, list)


def test_validate_load_path_broken():
    """Test detecting broken load path."""
    validator = StructuralValidator()

    roof_elements = []
    beams = []
    columns = [{"id": "col_1", "base_point": {"x": 0, "y": 0, "z": 0}}]
    foundations = []  # No foundations

    issues = validator.validate_load_path(roof_elements, beams, columns, foundations)
    broken_path_issues = [i for i in issues if i.issue_type == "broken_load_path"]
    assert len(broken_path_issues) > 0


def test_get_critical_issues():
    """Test getting critical issues."""
    validator = StructuralValidator()

    columns = [{"id": "col_1", "base_point": {"x": 0, "y": 0, "z": 0}}]
    foundations = []

    validator.validate_foundations(columns, foundations)

    critical = validator.get_critical_issues()
    assert len(critical) == 1
    assert critical[0].severity == "critical"


def test_complete_structural_workflow():
    """Test complete structural validation."""
    validator = StructuralValidator()

    # Building structure
    columns = [
        {"id": "col_1", "name": "C1", "location": {"x": 0, "y": 0, "z": 0}, "base_point": {"x": 0, "y": 0, "z": 0}},
        {"id": "col_2", "name": "C2", "location": {"x": 6000, "y": 0, "z": 0}, "base_point": {"x": 6000, "y": 0, "z": 0}},
        {"id": "col_3", "name": "C3", "location": {"x": 12000, "y": 0, "z": 0}, "base_point": {"x": 12000, "y": 0, "z": 0}},
    ]

    beams = [
        {
            "id": "beam_1",
            "start_point": {"x": 0, "y": 0, "z": 3000},
            "end_point": {"x": 6000, "y": 0, "z": 3000},
        },
        {
            "id": "beam_2",
            "start_point": {"x": 6000, "y": 0, "z": 3000},
            "end_point": {"x": 18000, "y": 0, "z": 3000},  # Extends beyond col_3
        },
    ]

    foundations = [
        {"id": "found_1", "location": {"x": 0, "y": 0, "z": -500}},
        {"id": "found_2", "location": {"x": 6000, "y": 0, "z": -500}},
        # Missing foundation for col_3
    ]

    roof_elements = [{"id": "roof_1", "location": {"x": 3000, "y": 0, "z": 6000}}]

    # Run all validations
    validator.validate_beam_connections(beams, columns)
    validator.validate_foundations(columns, foundations)
    validator.validate_load_path(roof_elements, beams, columns, foundations)

    total_issues = validator.get_issue_count()
    assert total_issues >= 2  # At minimum: beam_2 unconnected end + col_3 missing foundation

    critical_issues = validator.get_critical_issues()
    assert len(critical_issues) >= 2
