"""Test MEP connectivity validation."""

import pytest

from model_checker.mep import MEPConnectivityIssue, MEPConnectivityValidator


def test_create_mep_validator():
    """Test creating MEP connectivity validator."""
    validator = MEPConnectivityValidator()
    assert len(validator.issues) == 0


def test_validate_duct_connections_valid():
    """Test validating properly connected ducts."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply Air", "type": "duct"}]

    ducts = [
        {
            "id": "duct_1",
            "system_id": "sys_1",
            "start_connector": {"connected": True},
            "end_connector": {"connected": True},
        },
        {
            "id": "duct_2",
            "system_id": "sys_1",
            "start_connector": {"connected": True},
            "end_connector": {"connected": True},
        },
    ]

    issues = validator.validate_duct_connections(ducts, systems)
    assert len(issues) == 0


def test_validate_duct_no_system():
    """Test detecting ducts not in any system."""
    validator = MEPConnectivityValidator()

    systems = []
    ducts = [
        {
            "id": "duct_1",
            "start_connector": {"connected": True},
            "end_connector": {"connected": True},
        }
    ]

    issues = validator.validate_duct_connections(ducts, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "no_system"


def test_validate_duct_invalid_system():
    """Test detecting ducts with invalid system references."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply Air", "type": "duct"}]

    ducts = [
        {
            "id": "duct_1",
            "system_id": "sys_999",  # Invalid system ID
            "start_connector": {"connected": True},
            "end_connector": {"connected": True},
        }
    ]

    issues = validator.validate_duct_connections(ducts, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "invalid_system"


def test_validate_duct_disconnected_start():
    """Test detecting ducts with disconnected start connector."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply Air", "type": "duct"}]

    ducts = [
        {
            "id": "duct_1",
            "system_id": "sys_1",
            "start_connector": {"connected": False},
            "end_connector": {"connected": True},
        }
    ]

    issues = validator.validate_duct_connections(ducts, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "disconnected_start"
    assert issues[0].system_name == "Supply Air"


def test_validate_duct_disconnected_end():
    """Test detecting ducts with disconnected end connector."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Return Air", "type": "duct"}]

    ducts = [
        {
            "id": "duct_1",
            "system_id": "sys_1",
            "start_connector": {"connected": True},
            "end_connector": {"connected": False},
        }
    ]

    issues = validator.validate_duct_connections(ducts, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "disconnected_end"


def test_validate_duct_both_disconnected():
    """Test detecting ducts with both connectors disconnected."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply Air", "type": "duct"}]

    ducts = [
        {
            "id": "duct_1",
            "system_id": "sys_1",
            "start_connector": {"connected": False},
            "end_connector": {"connected": False},
        }
    ]

    issues = validator.validate_duct_connections(ducts, systems)
    assert len(issues) == 2  # Both start and end issues


def test_validate_pipe_connections_valid():
    """Test validating properly connected pipes."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Domestic Cold Water", "type": "pipe"}]

    pipes = [
        {
            "id": "pipe_1",
            "system_id": "sys_1",
            "connectors": [{"connected": True}, {"connected": True}],
        }
    ]

    issues = validator.validate_pipe_connections(pipes, systems)
    assert len(issues) == 0


def test_validate_pipe_no_system():
    """Test detecting pipes not in any system."""
    validator = MEPConnectivityValidator()

    systems = []
    pipes = [{"id": "pipe_1", "connectors": [{"connected": True}, {"connected": True}]}]

    issues = validator.validate_pipe_connections(pipes, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "no_system"


def test_validate_pipe_multiple_disconnected():
    """Test detecting pipes with multiple disconnected connectors."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Hot Water", "type": "pipe"}]

    pipes = [
        {
            "id": "pipe_1",
            "system_id": "sys_1",
            "connectors": [{"connected": False}, {"connected": False}],
        }
    ]

    issues = validator.validate_pipe_connections(pipes, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "multiple_disconnected"


def test_validate_system_equipment_valid():
    """Test validating properly connected equipment."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply Air", "type": "duct"}]

    equipment = [
        {"id": "at_1", "type": "air_terminal", "system_id": "sys_1"},
        {"id": "at_2", "type": "air_terminal", "system_id": "sys_1"},
    ]

    issues = validator.validate_system_equipment(equipment, systems)
    assert len(issues) == 0


def test_validate_equipment_no_system():
    """Test detecting equipment not connected to any system."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply Air", "type": "duct"}]

    equipment = [{"id": "at_1", "type": "air_terminal"}]  # No system_id

    issues = validator.validate_system_equipment(equipment, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "no_system"


def test_validate_equipment_invalid_system():
    """Test detecting equipment with invalid system reference."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply Air", "type": "duct"}]

    equipment = [{"id": "at_1", "type": "air_terminal", "system_id": "sys_999"}]

    issues = validator.validate_system_equipment(equipment, systems)
    assert len(issues) == 1
    assert issues[0].issue_type == "invalid_system"


def test_find_isolated_elements():
    """Test finding isolated MEP elements."""
    validator = MEPConnectivityValidator()

    elements = [
        {
            "id": "elem_1",
            "type": "duct",
            "connectors": [{"connected": False}, {"connected": False}],
        },
        {
            "id": "elem_2",
            "type": "pipe",
            "connectors": [{"connected": True}, {"connected": True}],
        },
    ]

    issues = validator.find_isolated_elements(elements)
    assert len(issues) == 1
    assert issues[0].element_id == "elem_1"
    assert issues[0].issue_type == "isolated"


def test_find_elements_no_connectors():
    """Test finding elements with no connectors."""
    validator = MEPConnectivityValidator()

    elements = [
        {"id": "elem_1", "type": "duct", "connectors": []},
        {"id": "elem_2", "type": "pipe"},  # No connectors field
    ]

    issues = validator.find_isolated_elements(elements)
    assert len(issues) == 2
    assert all(issue.issue_type == "no_connectors" for issue in issues)


def test_get_issues():
    """Test getting all issues."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply", "type": "duct"}]
    ducts = [{"id": "duct_1"}]  # No system_id

    validator.validate_duct_connections(ducts, systems)
    issues = validator.get_issues()

    assert len(issues) == 1


def test_get_issues_by_type():
    """Test filtering issues by type."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply", "type": "duct"}]

    ducts = [
        {"id": "duct_1"},  # No system
        {
            "id": "duct_2",
            "system_id": "sys_1",
            "start_connector": {"connected": False},
            "end_connector": {"connected": True},
        },  # Disconnected start
    ]

    validator.validate_duct_connections(ducts, systems)

    no_system_issues = validator.get_issues_by_type("no_system")
    disconnected_issues = validator.get_issues_by_type("disconnected_start")

    assert len(no_system_issues) == 1
    assert len(disconnected_issues) == 1


def test_get_issues_by_system():
    """Test filtering issues by system name."""
    validator = MEPConnectivityValidator()

    systems = [
        {"id": "sys_1", "name": "Supply Air", "type": "duct"},
        {"id": "sys_2", "name": "Return Air", "type": "duct"},
    ]

    ducts = [
        {
            "id": "duct_1",
            "system_id": "sys_1",
            "start_connector": {"connected": False},
            "end_connector": {"connected": True},
        },
        {
            "id": "duct_2",
            "system_id": "sys_2",
            "start_connector": {"connected": False},
            "end_connector": {"connected": True},
        },
    ]

    validator.validate_duct_connections(ducts, systems)

    supply_issues = validator.get_issues_by_system("Supply Air")
    return_issues = validator.get_issues_by_system("Return Air")

    assert len(supply_issues) == 1
    assert len(return_issues) == 1


def test_clear_issues():
    """Test clearing issues."""
    validator = MEPConnectivityValidator()

    systems = []
    ducts = [{"id": "duct_1"}]

    validator.validate_duct_connections(ducts, systems)
    assert len(validator.issues) > 0

    validator.clear_issues()
    assert len(validator.issues) == 0


def test_get_issue_count():
    """Test getting issue count."""
    validator = MEPConnectivityValidator()

    systems = [{"id": "sys_1", "name": "Supply", "type": "duct"}]
    ducts = [
        {"id": "duct_1"},
        {"id": "duct_2"},
        {"id": "duct_3"},
    ]

    validator.validate_duct_connections(ducts, systems)
    assert validator.get_issue_count() == 3


def test_complete_mep_workflow():
    """Test complete MEP connectivity validation workflow."""
    validator = MEPConnectivityValidator()

    # Define MEP systems
    systems = [
        {"id": "hvac_supply", "name": "Supply Air System", "type": "duct"},
        {"id": "hvac_return", "name": "Return Air System", "type": "duct"},
        {"id": "dhw", "name": "Domestic Hot Water", "type": "pipe"},
    ]

    # Define ducts
    ducts = [
        {
            "id": "duct_1",
            "system_id": "hvac_supply",
            "start_connector": {"connected": True},
            "end_connector": {"connected": True},
        },
        {
            "id": "duct_2",
            "system_id": "hvac_supply",
            "start_connector": {"connected": False},  # Issue
            "end_connector": {"connected": True},
        },
        {"id": "duct_3"},  # No system - Issue
    ]

    # Define pipes
    pipes = [
        {
            "id": "pipe_1",
            "system_id": "dhw",
            "connectors": [{"connected": True}, {"connected": True}],
        },
        {
            "id": "pipe_2",
            "system_id": "dhw",
            "connectors": [{"connected": False}, {"connected": False}],  # Issue
        },
    ]

    # Define equipment
    equipment = [
        {"id": "at_1", "type": "air_terminal", "system_id": "hvac_supply"},
        {"id": "at_2", "type": "air_terminal"},  # No system - Issue
        {"id": "fix_1", "type": "fixture", "system_id": "dhw"},
    ]

    # Run validations
    validator.validate_duct_connections(ducts, systems)
    validator.validate_pipe_connections(pipes, systems)
    validator.validate_system_equipment(equipment, systems)

    # Check results
    total_issues = validator.get_issue_count()
    assert total_issues == 4  # 2 duct + 1 pipe + 1 equipment

    supply_issues = validator.get_issues_by_system("Supply Air System")
    assert len(supply_issues) == 1  # duct_2 disconnected start

    no_system_issues = validator.get_issues_by_type("no_system")
    assert len(no_system_issues) == 2  # duct_3 and at_2
