"""Test the validator and report functionality."""

from datetime import datetime

import pytest

from model_checker import (
    Rule,
    RuleEngine,
    RuleSeverity,
    ValidationIssue,
    ValidationReport,
    Validator,
)


def test_create_validation_issue():
    """Test creating a validation issue."""
    issue = ValidationIssue(
        rule_id="test_rule",
        rule_name="Test Rule",
        severity=RuleSeverity.HIGH,
        category="testing",
        element_id="elem_123",
        description="Test issue description",
    )

    assert issue.rule_id == "test_rule"
    assert issue.rule_name == "Test Rule"
    assert issue.severity == RuleSeverity.HIGH
    assert issue.category == "testing"
    assert issue.element_id == "elem_123"
    assert issue.description == "Test issue description"
    assert isinstance(issue.timestamp, datetime)


def test_validation_issue_to_dict():
    """Test converting validation issue to dictionary."""
    issue = ValidationIssue(
        rule_id="wall_height",
        rule_name="Wall Height Check",
        severity=RuleSeverity.CRITICAL,
        category="geometry",
        element_id=12345,
        description="Wall height below minimum",
        location={"x": 100, "y": 200, "z": 0},
    )

    data = issue.to_dict()

    assert data["rule_id"] == "wall_height"
    assert data["rule_name"] == "Wall Height Check"
    assert data["severity"] == "critical"
    assert data["category"] == "geometry"
    assert data["element_id"] == 12345
    assert data["description"] == "Wall height below minimum"
    assert data["location"] == {"x": 100, "y": 200, "z": 0}
    assert "timestamp" in data


def test_create_validation_report():
    """Test creating a validation report."""
    report = ValidationReport(project_name="Test Project")

    assert report.project_name == "Test Project"
    assert isinstance(report.timestamp, datetime)
    assert len(report.issues) == 0
    assert report.total_elements_checked == 0
    assert report.rules_executed == 0


def test_add_issue_to_report():
    """Test adding issues to a report."""
    report = ValidationReport(project_name="Test Project")

    issue1 = ValidationIssue(
        rule_id="rule_1",
        rule_name="Rule 1",
        severity=RuleSeverity.HIGH,
        category="test",
        element_id="elem_1",
        description="Issue 1",
    )

    issue2 = ValidationIssue(
        rule_id="rule_2",
        rule_name="Rule 2",
        severity=RuleSeverity.MEDIUM,
        category="test",
        element_id="elem_2",
        description="Issue 2",
    )

    report.add_issue(issue1)
    report.add_issue(issue2)

    assert len(report.issues) == 2
    assert report.issues[0] == issue1
    assert report.issues[1] == issue2


def test_get_issues_by_severity():
    """Test filtering issues by severity."""
    report = ValidationReport(project_name="Test")

    critical_issue = ValidationIssue(
        rule_id="r1",
        rule_name="Critical Rule",
        severity=RuleSeverity.CRITICAL,
        category="test",
        element_id="e1",
        description="Critical issue",
    )

    high_issue = ValidationIssue(
        rule_id="r2",
        rule_name="High Rule",
        severity=RuleSeverity.HIGH,
        category="test",
        element_id="e2",
        description="High issue",
    )

    low_issue = ValidationIssue(
        rule_id="r3",
        rule_name="Low Rule",
        severity=RuleSeverity.LOW,
        category="test",
        element_id="e3",
        description="Low issue",
    )

    report.add_issue(critical_issue)
    report.add_issue(high_issue)
    report.add_issue(low_issue)

    critical_issues = report.get_issues_by_severity(RuleSeverity.CRITICAL)
    high_issues = report.get_issues_by_severity(RuleSeverity.HIGH)
    low_issues = report.get_issues_by_severity(RuleSeverity.LOW)

    assert len(critical_issues) == 1
    assert critical_issues[0] == critical_issue
    assert len(high_issues) == 1
    assert high_issues[0] == high_issue
    assert len(low_issues) == 1
    assert low_issues[0] == low_issue


def test_get_issues_by_category():
    """Test filtering issues by category."""
    report = ValidationReport(project_name="Test")

    geometry_issue = ValidationIssue(
        rule_id="g1",
        rule_name="Geometry Rule",
        severity=RuleSeverity.HIGH,
        category="geometry",
        element_id="e1",
        description="Geometry issue",
    )

    naming_issue = ValidationIssue(
        rule_id="n1",
        rule_name="Naming Rule",
        severity=RuleSeverity.MEDIUM,
        category="naming",
        element_id="e2",
        description="Naming issue",
    )

    report.add_issue(geometry_issue)
    report.add_issue(naming_issue)

    geometry_issues = report.get_issues_by_category("geometry")
    naming_issues = report.get_issues_by_category("naming")

    assert len(geometry_issues) == 1
    assert geometry_issues[0] == geometry_issue
    assert len(naming_issues) == 1
    assert naming_issues[0] == naming_issue


def test_report_counts():
    """Test report counting methods."""
    report = ValidationReport(project_name="Test")

    # Add various severity issues
    for i in range(3):
        report.add_issue(
            ValidationIssue(
                rule_id=f"c{i}",
                rule_name="Critical",
                severity=RuleSeverity.CRITICAL,
                category="test",
                element_id=f"e{i}",
                description="Critical",
            )
        )

    for i in range(2):
        report.add_issue(
            ValidationIssue(
                rule_id=f"h{i}",
                rule_name="High",
                severity=RuleSeverity.HIGH,
                category="test",
                element_id=f"e{i}",
                description="High",
            )
        )

    report.add_issue(
        ValidationIssue(
            rule_id="m1",
            rule_name="Medium",
            severity=RuleSeverity.MEDIUM,
            category="test",
            element_id="e1",
            description="Medium",
        )
    )

    assert report.get_critical_count() == 3
    assert report.get_high_count() == 2
    assert report.get_total_issues() == 6


def test_validation_report_to_dict():
    """Test converting validation report to dictionary."""
    report = ValidationReport(project_name="Sample Project")
    report.total_elements_checked = 100
    report.rules_executed = 25

    issue = ValidationIssue(
        rule_id="test_rule",
        rule_name="Test Rule",
        severity=RuleSeverity.HIGH,
        category="test",
        element_id="elem_1",
        description="Test issue",
    )

    report.add_issue(issue)

    data = report.to_dict()

    assert data["project_name"] == "Sample Project"
    assert data["total_elements_checked"] == 100
    assert data["rules_executed"] == 25
    assert data["total_issues"] == 1
    assert data["critical_issues"] == 0
    assert data["high_issues"] == 1
    assert len(data["issues"]) == 1
    assert "timestamp" in data


def test_create_validator():
    """Test creating a validator."""
    engine = RuleEngine()
    validator = Validator(engine)

    assert validator.rule_engine == engine
    assert validator.current_report is None


def test_validator_create_report():
    """Test validator creating a report."""
    engine = RuleEngine()
    validator = Validator(engine)

    report = validator.create_report("My Project")

    assert report.project_name == "My Project"
    assert validator.current_report == report


def test_validate_element():
    """Test validating an element against rules."""
    engine = RuleEngine()
    validator = Validator(engine)
    validator.create_report("Test Project")

    # Create rules
    min_height_rule = Rule(
        id="min_height",
        name="Minimum Height",
        description="Height must be >= 2400",
        category="geometry",
        severity=RuleSeverity.CRITICAL,
        check_function=lambda elem: elem.get("height", 0) >= 2400,
    )

    max_width_rule = Rule(
        id="max_width",
        name="Maximum Width",
        description="Width must be <= 1000",
        category="geometry",
        severity=RuleSeverity.HIGH,
        check_function=lambda elem: elem.get("width", 0) <= 1000,
    )

    # Validate valid element
    valid_element = {"height": 3000, "width": 800}
    issues = validator.validate_element(
        valid_element, "elem_1", [min_height_rule, max_width_rule]
    )

    assert len(issues) == 0

    # Validate invalid element
    invalid_element = {"height": 2000, "width": 1200}
    issues = validator.validate_element(
        invalid_element, "elem_2", [min_height_rule, max_width_rule]
    )

    assert len(issues) == 2
    assert issues[0].rule_id == "min_height"
    assert issues[0].severity == RuleSeverity.CRITICAL
    assert issues[1].rule_id == "max_width"
    assert issues[1].severity == RuleSeverity.HIGH


def test_validator_adds_to_report():
    """Test that validator adds issues to current report."""
    engine = RuleEngine()
    validator = Validator(engine)
    report = validator.create_report("Test Project")

    rule = Rule(
        id="test_rule",
        name="Test Rule",
        description="Test",
        category="test",
        severity=RuleSeverity.MEDIUM,
        check_function=lambda elem: elem > 10,
    )

    validator.validate_element(5, "elem_1", [rule])

    assert len(report.issues) == 1
    assert report.issues[0].rule_id == "test_rule"


def test_complete_validation_workflow():
    """Test complete validation workflow with report generation."""
    # Setup
    engine = RuleEngine()
    validator = Validator(engine)

    # Create report
    report = validator.create_report("Office Building Project")
    report.total_elements_checked = 5
    report.rules_executed = 3

    # Define rules for wall validation
    min_height_rule = Rule(
        id="wall_min_height",
        name="Minimum Wall Height",
        description="Wall height must be at least 2400mm",
        category="walls",
        severity=RuleSeverity.CRITICAL,
        check_function=lambda wall: wall.get("height", 0) >= 2400,
    )

    max_length_rule = Rule(
        id="wall_max_length",
        name="Maximum Wall Length",
        description="Wall length should not exceed 12000mm",
        category="walls",
        severity=RuleSeverity.HIGH,
        check_function=lambda wall: wall.get("length", 0) <= 12000,
    )

    naming_rule = Rule(
        id="wall_naming",
        name="Wall Naming Convention",
        description="Wall name should start with 'W-'",
        category="naming",
        severity=RuleSeverity.MEDIUM,
        check_function=lambda wall: wall.get("name", "").startswith("W-"),
    )

    rules = [min_height_rule, max_length_rule, naming_rule]

    # Validate elements
    walls = [
        {"id": "wall_1", "height": 3000, "length": 6000, "name": "W-Exterior-001"},  # Valid
        {"id": "wall_2", "height": 2000, "length": 5000, "name": "W-Interior-002"},  # Too short
        {"id": "wall_3", "height": 2800, "length": 15000, "name": "Wall-003"},  # Too long, bad name
        {"id": "wall_4", "height": 2500, "length": 8000, "name": "Interior"},  # Bad name
    ]

    for wall in walls:
        validator.validate_element(wall, wall["id"], rules)

    # Verify report
    assert report.get_total_issues() == 4  # 1 height + 1 length + 2 naming issues
    assert report.get_critical_count() == 1  # wall_2 height
    assert report.get_high_count() == 1  # wall_3 length

    wall_issues = report.get_issues_by_category("walls")
    naming_issues = report.get_issues_by_category("naming")

    assert len(wall_issues) == 2
    assert len(naming_issues) == 2

    # Convert to dict
    report_dict = report.to_dict()
    assert report_dict["project_name"] == "Office Building Project"
    assert report_dict["total_issues"] == 4
    assert report_dict["critical_issues"] == 1
    assert report_dict["high_issues"] == 1
