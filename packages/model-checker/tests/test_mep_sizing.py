"""Test MEP sizing and clearance validation."""

import pytest

from model_checker.mep import MEPClearanceValidator, MEPSizingValidator


# Sizing Tests
def test_validate_duct_sizing_valid():
    """Test validating properly sized ducts."""
    validator = MEPSizingValidator()

    ducts = [
        {"id": "duct_1", "width": 500, "height": 300, "velocity": 8.0},
        {"id": "duct_2", "width": 400, "height": 400, "velocity": 9.5},
    ]

    issues = validator.validate_duct_sizing(ducts, max_velocity=10.0)
    assert len(issues) == 0


def test_validate_duct_undersized():
    """Test detecting undersized ducts."""
    validator = MEPSizingValidator()

    ducts = [{"id": "duct_1", "width": 50, "height": 50, "velocity": 5.0}]

    issues = validator.validate_duct_sizing(ducts, min_size=100.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "undersized"


def test_validate_duct_oversized():
    """Test detecting oversized ducts."""
    validator = MEPSizingValidator()

    ducts = [{"id": "duct_1", "width": 2500, "height": 1500, "velocity": 5.0}]

    issues = validator.validate_duct_sizing(ducts, max_size=2000.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "oversized"


def test_validate_duct_excessive_velocity():
    """Test detecting excessive duct velocity."""
    validator = MEPSizingValidator()

    ducts = [{"id": "duct_1", "width": 300, "height": 300, "velocity": 15.0}]

    issues = validator.validate_duct_sizing(ducts, max_velocity=10.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "excessive_velocity"


def test_validate_pipe_sizing_valid():
    """Test validating properly sized pipes."""
    validator = MEPSizingValidator()

    pipes = [
        {"id": "pipe_1", "diameter": 50, "velocity": 2.0},
        {"id": "pipe_2", "diameter": 100, "velocity": 2.5},
    ]

    issues = validator.validate_pipe_sizing(pipes, max_velocity=3.0)
    assert len(issues) == 0


def test_validate_pipe_undersized():
    """Test detecting undersized pipes."""
    validator = MEPSizingValidator()

    pipes = [{"id": "pipe_1", "diameter": 10, "velocity": 2.0}]

    issues = validator.validate_pipe_sizing(pipes, min_diameter=15.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "undersized"


def test_validate_pipe_oversized():
    """Test detecting oversized pipes."""
    validator = MEPSizingValidator()

    pipes = [{"id": "pipe_1", "diameter": 800, "velocity": 1.0}]

    issues = validator.validate_pipe_sizing(pipes, max_diameter=600.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "oversized"


def test_validate_pipe_excessive_velocity():
    """Test detecting excessive pipe velocity."""
    validator = MEPSizingValidator()

    pipes = [{"id": "pipe_1", "diameter": 25, "velocity": 5.0}]

    issues = validator.validate_pipe_sizing(pipes, max_velocity=3.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "excessive_velocity"


# Clearance Tests
def test_validate_headroom_clearance_valid():
    """Test validating proper headroom clearance."""
    validator = MEPClearanceValidator()

    elements = [
        {"id": "duct_1", "type": "duct", "elevation": 2500, "height": 300},
        {"id": "pipe_1", "type": "pipe", "elevation": 2400, "height": 100},
    ]

    issues = validator.validate_headroom_clearance(elements, min_clearance=2100.0)
    assert len(issues) == 0


def test_validate_headroom_insufficient():
    """Test detecting insufficient headroom."""
    validator = MEPClearanceValidator()

    elements = [
        {"id": "duct_1", "type": "duct", "elevation": 2200, "height": 400}
    ]  # Bottom at 2000mm

    issues = validator.validate_headroom_clearance(elements, min_clearance=2100.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "insufficient_headroom"


def test_validate_access_clearance_valid():
    """Test validating proper access clearance."""
    validator = MEPClearanceValidator()

    equipment = [
        {"id": "ahu_1", "type": "air_handler", "access_clearance": 800},
        {"id": "pump_1", "type": "pump", "access_clearance": 1000},
    ]

    issues = validator.validate_access_clearance(equipment, min_access_clearance=600.0)
    assert len(issues) == 0


def test_validate_access_insufficient():
    """Test detecting insufficient access clearance."""
    validator = MEPClearanceValidator()

    equipment = [{"id": "ahu_1", "type": "air_handler", "access_clearance": 400}]

    issues = validator.validate_access_clearance(equipment, min_access_clearance=600.0)
    assert len(issues) == 1
    assert issues[0].issue_type == "insufficient_access"


def test_complete_mep_sizing_workflow():
    """Test complete MEP sizing and clearance validation."""
    sizing_validator = MEPSizingValidator()
    clearance_validator = MEPClearanceValidator()

    # Validate duct sizing
    ducts = [
        {"id": "duct_1", "width": 500, "height": 300, "velocity": 8.0},  # OK
        {"id": "duct_2", "width": 50, "height": 50, "velocity": 5.0},  # Undersized
        {"id": "duct_3", "width": 600, "height": 400, "velocity": 12.0},  # Excessive velocity
    ]

    # Validate pipe sizing
    pipes = [
        {"id": "pipe_1", "diameter": 50, "velocity": 2.0},  # OK
        {"id": "pipe_2", "diameter": 10, "velocity": 1.5},  # Undersized
        {"id": "pipe_3", "diameter": 100, "velocity": 4.0},  # Excessive velocity
    ]

    # Validate clearances
    elements = [
        {"id": "duct_4", "type": "duct", "elevation": 2200, "height": 400},  # Insufficient headroom
    ]

    equipment = [
        {"id": "ahu_1", "type": "air_handler", "access_clearance": 400}  # Insufficient access
    ]

    sizing_validator.validate_duct_sizing(ducts)
    sizing_validator.validate_pipe_sizing(pipes)
    clearance_validator.validate_headroom_clearance(elements)
    clearance_validator.validate_access_clearance(equipment)

    assert len(sizing_validator.get_issues()) == 4  # 2 ducts + 2 pipes
    assert len(clearance_validator.get_issues()) == 2  # 1 headroom + 1 access
