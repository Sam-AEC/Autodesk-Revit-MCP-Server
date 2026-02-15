"""Test level and grid validation."""

import pytest

from model_checker.standards import LevelGridValidator, LevelValidationIssue


def test_create_level_grid_validator():
    """Test creating level/grid validator."""
    validator = LevelGridValidator()
    assert len(validator.issues) == 0


def test_validate_level_naming_valid():
    """Test validating correct level naming."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "L01", "elevation": 0.0},
        {"id": "level_2", "name": "L02", "elevation": 3000.0},
        {"id": "level_3", "name": "L03", "elevation": 6000.0},
    ]

    issues = validator.validate_level_naming(levels)
    assert len(issues) == 0


def test_validate_level_naming_invalid():
    """Test detecting invalid level names."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "Level 01", "elevation": 0.0},
        {"id": "level_2", "name": "Floor 2", "elevation": 3000.0},
        {"id": "level_3", "name": "L03", "elevation": 6000.0},  # Valid
    ]

    issues = validator.validate_level_naming(levels)
    assert len(issues) == 2
    assert issues[0].level_name == "Level 01"
    assert issues[0].issue_type == "naming"


def test_validate_level_naming_custom_pattern():
    """Test level naming with custom pattern."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "FL-01", "elevation": 0.0},
        {"id": "level_2", "name": "FL-02", "elevation": 3000.0},
    ]

    # Should fail default pattern
    issues = validator.validate_level_naming(levels)
    assert len(issues) == 2

    # Should pass custom pattern
    validator.clear_issues()
    issues = validator.validate_level_naming(levels, pattern=r"^FL-\d{2}$")
    assert len(issues) == 0


def test_validate_level_spacing_valid():
    """Test validating correct level spacing."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "L01", "elevation": 0.0},
        {"id": "level_2", "name": "L02", "elevation": 3500.0},
        {"id": "level_3", "name": "L03", "elevation": 7000.0},
    ]

    # Default spacing 3000-5000mm
    issues = validator.validate_level_spacing(levels)
    assert len(issues) == 0


def test_validate_level_spacing_too_small():
    """Test detecting levels that are too close together."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "L01", "elevation": 0.0},
        {"id": "level_2", "name": "L02", "elevation": 2000.0},  # Only 2000mm spacing
    ]

    issues = validator.validate_level_spacing(levels, min_spacing=3000.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "spacing_too_small"
    assert issues[0].level_name == "L02"


def test_validate_level_spacing_too_large():
    """Test detecting levels that are too far apart."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "L01", "elevation": 0.0},
        {"id": "level_2", "name": "L02", "elevation": 6000.0},  # 6000mm spacing
    ]

    issues = validator.validate_level_spacing(levels, max_spacing=5000.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "spacing_too_large"


def test_validate_level_spacing_multiple_levels():
    """Test spacing validation with multiple levels."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "L01", "elevation": 0.0},
        {"id": "level_2", "name": "L02", "elevation": 2500.0},  # Too small
        {"id": "level_3", "name": "L03", "elevation": 6000.0},  # OK
        {"id": "level_4", "name": "L04", "elevation": 12000.0},  # Too large
    ]

    issues = validator.validate_level_spacing(levels, min_spacing=3000.0, max_spacing=5000.0)
    assert len(issues) == 2


def test_validate_grid_naming_valid():
    """Test validating correct grid names."""
    validator = LevelGridValidator()

    grids = [
        {"id": "grid_1", "name": "A"},
        {"id": "grid_2", "name": "B"},
        {"id": "grid_3", "name": "1"},
        {"id": "grid_4", "name": "2"},
    ]

    issues = validator.validate_grid_naming(grids)
    assert len(issues) == 0


def test_validate_grid_naming_invalid():
    """Test detecting invalid grid names."""
    validator = LevelGridValidator()

    grids = [
        {"id": "grid_1", "name": "A"},  # Valid
        {"id": "grid_2", "name": "Grid-B"},  # Invalid
        {"id": "grid_3", "name": "1"},  # Valid
        {"id": "grid_4", "name": "100"},  # Invalid (3 digits)
    ]

    issues = validator.validate_grid_naming(grids)
    assert len(issues) == 2
    assert issues[0].level_name == "Grid-B"
    assert issues[1].level_name == "100"


def test_validate_grid_spacing_horizontal():
    """Test horizontal grid spacing validation."""
    validator = LevelGridValidator()

    grids = [
        {"id": "grid_1", "name": "1", "orientation": "horizontal", "position": 0.0},
        {"id": "grid_2", "name": "2", "orientation": "horizontal", "position": 6000.0},
        {"id": "grid_3", "name": "3", "orientation": "horizontal", "position": 12000.0},
    ]

    issues = validator.validate_grid_spacing(grids, min_spacing=3000.0, max_spacing=12000.0)
    assert len(issues) == 0


def test_validate_grid_spacing_vertical():
    """Test vertical grid spacing validation."""
    validator = LevelGridValidator()

    grids = [
        {"id": "grid_a", "name": "A", "orientation": "vertical", "position": 0.0},
        {"id": "grid_b", "name": "B", "orientation": "vertical", "position": 8000.0},
    ]

    issues = validator.validate_grid_spacing(grids, min_spacing=3000.0, max_spacing=12000.0)
    assert len(issues) == 0


def test_validate_grid_spacing_too_small():
    """Test detecting grids that are too close."""
    validator = LevelGridValidator()

    grids = [
        {"id": "grid_1", "name": "1", "orientation": "horizontal", "position": 0.0},
        {"id": "grid_2", "name": "2", "orientation": "horizontal", "position": 2000.0},
    ]

    issues = validator.validate_grid_spacing(grids, min_spacing=3000.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "grid_spacing_too_small"


def test_validate_grid_spacing_too_large():
    """Test detecting grids that are too far apart."""
    validator = LevelGridValidator()

    grids = [
        {"id": "grid_1", "name": "1", "orientation": "horizontal", "position": 0.0},
        {"id": "grid_2", "name": "2", "orientation": "horizontal", "position": 15000.0},
    ]

    issues = validator.validate_grid_spacing(grids, max_spacing=12000.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "grid_spacing_too_large"


def test_validate_mixed_grid_orientations():
    """Test validating grids with mixed orientations."""
    validator = LevelGridValidator()

    grids = [
        # Horizontal grids
        {"id": "grid_1", "name": "1", "orientation": "horizontal", "position": 0.0},
        {"id": "grid_2", "name": "2", "orientation": "horizontal", "position": 6000.0},
        # Vertical grids
        {"id": "grid_a", "name": "A", "orientation": "vertical", "position": 0.0},
        {"id": "grid_b", "name": "B", "orientation": "vertical", "position": 8000.0},
    ]

    issues = validator.validate_grid_spacing(grids, min_spacing=3000.0, max_spacing=12000.0)
    assert len(issues) == 0


def test_get_issues():
    """Test getting all issues."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "Bad Name", "elevation": 0.0},
        {"id": "level_2", "name": "L02", "elevation": 2000.0},
    ]

    validator.validate_level_naming(levels)
    validator.validate_level_spacing(levels, min_spacing=3000.0)

    issues = validator.get_issues()
    assert len(issues) == 2  # 1 naming + 1 spacing


def test_get_issues_by_type():
    """Test filtering issues by type."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "Bad Name", "elevation": 0.0},
        {"id": "level_2", "name": "L02", "elevation": 2000.0},
    ]

    validator.validate_level_naming(levels)
    validator.validate_level_spacing(levels, min_spacing=3000.0)

    naming_issues = validator.get_issues_by_type("naming")
    spacing_issues = validator.get_issues_by_type("spacing_too_small")

    assert len(naming_issues) == 1
    assert len(spacing_issues) == 1


def test_clear_issues():
    """Test clearing issues."""
    validator = LevelGridValidator()

    levels = [{"id": "level_1", "name": "Bad Name", "elevation": 0.0}]

    validator.validate_level_naming(levels)
    assert len(validator.issues) > 0

    validator.clear_issues()
    assert len(validator.issues) == 0


def test_get_issue_count():
    """Test getting issue count."""
    validator = LevelGridValidator()

    levels = [
        {"id": "level_1", "name": "Bad Name 1", "elevation": 0.0},
        {"id": "level_2", "name": "Bad Name 2", "elevation": 3000.0},
        {"id": "level_3", "name": "Bad Name 3", "elevation": 6000.0},
    ]

    validator.validate_level_naming(levels)
    assert validator.get_issue_count() == 3


def test_complete_validation_workflow():
    """Test complete level and grid validation workflow."""
    validator = LevelGridValidator()

    # Define building levels
    levels = [
        {"id": "level_b1", "name": "L-B1", "elevation": -3000.0},  # Bad name
        {"id": "level_g", "name": "L00", "elevation": 0.0},  # OK
        {"id": "level_1", "name": "L01", "elevation": 4000.0},  # OK
        {"id": "level_2", "name": "L02", "elevation": 8000.0},  # OK
        {"id": "level_roof", "name": "Roof", "elevation": 12000.0},  # Bad name
    ]

    # Define grids
    grids = [
        {"id": "grid_1", "name": "1", "orientation": "horizontal", "position": 0.0},
        {"id": "grid_2", "name": "2", "orientation": "horizontal", "position": 2000.0},  # Too close
        {"id": "grid_3", "name": "3", "orientation": "horizontal", "position": 8000.0},
        {"id": "grid_a", "name": "A", "orientation": "vertical", "position": 0.0},
        {"id": "grid_b", "name": "B-North", "orientation": "vertical", "position": 10000.0},  # Bad name
    ]

    # Run validations
    validator.validate_level_naming(levels)
    validator.validate_level_spacing(levels, min_spacing=3000.0, max_spacing=5000.0)
    validator.validate_grid_naming(grids)
    validator.validate_grid_spacing(grids, min_spacing=3000.0, max_spacing=12000.0)

    # Check results
    total_issues = validator.get_issue_count()
    assert total_issues > 0

    naming_issues = validator.get_issues_by_type("naming")
    assert len(naming_issues) == 2  # L-B1 and Roof

    grid_naming_issues = validator.get_issues_by_type("grid_naming")
    assert len(grid_naming_issues) == 1  # B-North

    spacing_issues = validator.get_issues_by_type("grid_spacing_too_small")
    assert len(spacing_issues) == 1  # Grid 2
